import random

import pytest

from vaanisetu import codec
from vaanisetu.languages import LANGUAGES
from vaanisetu.message import MessageAssembler, encode_message
from vaanisetu.packet import OVERHEAD, Packet, PacketError, Reassembler, crc16, fragment
from vaanisetu.phrases import PHRASES, SAMPLES
from vaanisetu.transport import LoopbackTransport, LossyLink, UdpTransport

ALL = [(lang, t) for lang in LANGUAGES for t in PHRASES[lang] + SAMPLES[lang]]


def test_all_languages_have_data():
    assert len(LANGUAGES) == 11
    for lang in LANGUAGES:
        assert PHRASES[lang] and SAMPLES[lang]


@pytest.mark.parametrize("lang,text", ALL)
def test_codec_roundtrip(lang, text):
    method, data = codec.encode(text, lang)
    assert codec.decode(method, data, lang) == text


@pytest.mark.parametrize("lang", LANGUAGES)
def test_codec_roundtrip_escapes_and_mixed(lang):
    text = "Hi ก \U0001F198 123 \x7f ‍ end"
    method, data = codec.encode(text, lang)
    assert codec.decode(method, data, lang) == text


def test_codec_nfc():
    method, data = codec.encode("é", "en")
    assert codec.decode(method, data, "en") == "é"


def test_codec_never_larger_than_compact():
    for lang, text in ALL:
        assert len(codec.encode(text, lang)[1]) <= len(codec.compact_encode(text, lang))


def test_indic_compact_is_one_byte_per_char():
    # Pure Devanagari/space text: exactly 1 byte per character (holds by construction).
    text = "मदद भेजो"
    assert len(codec.compact_encode(text, "hi")) == len(text)


def test_codec_rejects_garbage():
    with pytest.raises(codec.CodecError):
        codec.decode(1, b"\xff\xff\xff", "hi")
    with pytest.raises(codec.CodecError):
        codec.decode(0, b"\xff", "hi")
    with pytest.raises(codec.CodecError):
        codec.decode(7, b"", "hi")


def test_crc_known_vector():
    assert crc16(b"123456789") == 0x29B1


def test_packet_roundtrip_and_overhead():
    p = Packet(1, 9, 0, 1, b"abc", 1)
    raw = p.encode()
    assert len(raw) == OVERHEAD + 3
    assert Packet.decode(raw) == p


def test_crc_detects_every_single_bit_flip():
    raw = Packet(3, 200, 1, 3, b"hello world", 0).encode()
    for i in range(len(raw) * 8):
        bad = bytearray(raw)
        bad[i // 8] ^= 1 << (i % 8)
        with pytest.raises(PacketError):
            Packet.decode(bytes(bad))


def test_strict_validation():
    good = Packet(0, 0, 0, 1, b"x").encode()
    for bad in (b"", good[:-1], good + b"\x00", b"\x00" * 6):
        with pytest.raises(PacketError):
            Packet.decode(bad)
    for kw in ({"lang_id": 11}, {"msg_id": 256}, {"index": 1}, {"count": 17}, {"method": 2}):
        args = {"lang_id": 0, "msg_id": 0, "index": 0, "count": 1, "payload": b"", "method": 0}
        args.update(kw)
        with pytest.raises(PacketError):
            Packet(**args).encode()


def _rebuild(body: bytes) -> bytes:
    return body + crc16(body).to_bytes(2, "big")


def test_bad_version_and_lang_with_valid_crc():
    good = Packet(0, 0, 0, 1, b"").encode()[:-2]
    with pytest.raises(PacketError, match="version"):
        Packet.decode(_rebuild(bytes([2 << 5]) + good[1:]))
    with pytest.raises(PacketError, match="language"):
        Packet.decode(_rebuild(bytes([(1 << 5) | 15]) + good[1:]))


def test_fragment_and_reassemble_shuffled_with_duplicates():
    data = bytes(range(200))
    pkts = fragment(2, 5, 0, data, mtu=40)
    assert len(pkts) > 1 and all(len(p.encode()) <= 40 for p in pkts)
    raws = [p.encode() for p in pkts]
    stream = raws + raws[:2] + raws[-1:]
    random.Random(1).shuffle(stream)
    re_, done = Reassembler(), []
    for raw in stream:
        out = re_.add(Packet.decode(raw))
        if out is not None:
            done.append(out)
    assert done == [data]


def test_fragment_limits():
    with pytest.raises(PacketError):
        fragment(0, 0, 0, b"x" * 1000, mtu=OVERHEAD + 10)
    with pytest.raises(PacketError):
        fragment(0, 0, 0, b"x", mtu=OVERHEAD)


def test_reassembler_conflicts():
    re_ = Reassembler()
    re_.add(Packet(0, 1, 0, 2, b"a"))
    with pytest.raises(PacketError):
        re_.add(Packet(0, 1, 0, 2, b"b"))
    with pytest.raises(PacketError):
        re_.add(Packet(0, 1, 1, 3, b"b"))


def test_long_message_roundtrip_through_fragments():
    text = " ".join(SAMPLES["hi"] + SAMPLES["mr"] + SAMPLES["bn"])
    raws = encode_message(text, "hi", 7, mtu=24)
    assert len(raws) > 1 and all(len(r) <= 24 for r in raws)
    random.Random(2).shuffle(raws)
    asm, out = MessageAssembler(), None
    for r in raws + raws:
        out = asm.feed(r) or out
    assert out and out.text == text and out.lang == "hi" and out.msg_id == 7


def test_assembler_skips_corrupt():
    raw = bytearray(encode_message("Send help", "en")[0])
    raw[5] ^= 0xFF
    asm = MessageAssembler()
    assert asm.feed(bytes(raw)) is None and asm.dropped == 1


@pytest.mark.parametrize("lang", LANGUAGES)
def test_loopback_every_language(lang):
    a, b = LoopbackTransport.pair()
    for p in encode_message(PHRASES[lang][0], lang, 1):
        a.send(p)
    asm, msg = MessageAssembler(), None
    while (raw := b.recv()) is not None:
        msg = asm.feed(raw) or msg
    assert msg and msg.text == PHRASES[lang][0]


def test_single_packet_fits_small_mtu_for_short_phrases():
    # Holds for the bundled data: every phrase and sample fits one 100-byte packet.
    for lang, text in ALL:
        assert len(encode_message(text, lang, 0, mtu=100)) == 1


def test_lossy_link_with_repeats_and_mtu():
    a, b = LoopbackTransport.pair()
    link = LossyLink(a, drop_rate=0.3, mtu=24, seed=42)
    text = " ".join(SAMPLES["ta"] + PHRASES["ta"])
    raws = encode_message(text, "ta", 3, mtu=24)
    assert len(raws) > 1
    for _ in range(12):  # blind repetition as simple loss cover
        for r in raws:
            link.send(r)
    assert link.dropped > 0
    asm, msgs = MessageAssembler(), []
    while (raw := b.recv()) is not None:
        m = asm.feed(raw)
        if m:
            msgs.append(m)
    assert [m.text for m in msgs] == [text]
    with pytest.raises(ValueError):
        link.send(b"x" * 25)


def test_lossy_link_total_loss():
    a, b = LoopbackTransport.pair()
    link = LossyLink(a, drop_rate=1.0)
    link.send(b"x")
    assert b.recv() is None


def test_udp_roundtrip():
    rx = UdpTransport(bind=("127.0.0.1", 0))
    tx = UdpTransport(peer=rx.address)
    try:
        for p in encode_message("Send help", "en", 1):
            tx.send(p)
        data = rx.recv(timeout=2)
    except OSError:  # pragma: no cover
        pytest.skip("UDP unavailable")
    finally:
        tx.close()
        rx.close()
    assert MessageAssembler().feed(data).text == "Send help"


def test_retransmitted_message_delivered_once():
    asm, got = MessageAssembler(), []
    raws = encode_message("Send help, we need water now, boats and doctors please", "en", 4, mtu=20)
    for r in raws * 3:
        m = asm.feed(r)
        if m:
            got.append(m)
    assert len(got) == 1
