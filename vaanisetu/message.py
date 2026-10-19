"""Text <-> packets: glue between codec and packet layers."""

from __future__ import annotations

from dataclasses import dataclass

from . import codec
from .languages import lang_from_id, lang_id
from .packet import Packet, PacketError, Reassembler, fragment

DEFAULT_MTU = 64


@dataclass(frozen=True)
class Message:
    msg_id: int
    lang: str
    text: str


def encode_message(text: str, lang: str, msg_id: int = 0, mtu: int = DEFAULT_MTU) -> list[bytes]:
    method, data = codec.encode(text, lang)
    return [p.encode() for p in fragment(lang_id(lang), msg_id & 0xFF, method, data, mtu)]


class MessageAssembler:
    """Feed raw datagrams; get Messages out. Corrupt packets are counted and skipped."""

    def __init__(self) -> None:
        self._re = Reassembler()
        self._meta: dict[int, tuple[int, int]] = {}
        self.dropped = 0

    def feed(self, raw: bytes) -> Message | None:
        try:
            pkt = Packet.decode(raw)
            data = self._re.add(pkt)
        except PacketError:
            self.dropped += 1
            return None
        if data is None:
            return None
        try:
            text = codec.decode(pkt.method, data, lang_from_id(pkt.lang_id))
        except (codec.CodecError, ValueError):
            self.dropped += 1
            return None
        return Message(pkt.msg_id, lang_from_id(pkt.lang_id), text)
