"""Command line: send / receive / bench."""

from __future__ import annotations

import argparse
import statistics
import sys

from .languages import LANGUAGES
from .message import DEFAULT_MTU, MessageAssembler, encode_message
from .phrases import PHRASES, SAMPLES
from .speech import get_tts
from .transport import UdpTransport

DEFAULT_ADDR = "127.0.0.1:47474"


def _addr(s: str) -> tuple[str, int]:
    host, _, port = s.rpartition(":")
    return host or "127.0.0.1", int(port)


def cmd_send(a: argparse.Namespace) -> int:
    pkts = encode_message(a.text, a.lang, a.msg_id, a.mtu)
    t = UdpTransport(peer=_addr(a.to))
    for _ in range(a.repeat):
        for p in pkts:
            t.send(p)
    t.close()
    print(f"sent {len(pkts)} packet(s), {sum(map(len, pkts))} bytes, x{a.repeat} to {a.to}")
    return 0


def cmd_receive(a: argparse.Namespace) -> int:
    t = UdpTransport(bind=_addr(a.bind))
    asm, tts, got = MessageAssembler(), get_tts("text"), 0
    print(f"listening on {a.bind} ...", file=sys.stderr)
    try:
        while a.count == 0 or got < a.count:
            raw = t.recv(a.timeout)
            if raw is None:
                if a.timeout:
                    break
                continue
            msg = asm.feed(raw)
            if msg:
                got += 1
                tts.speak(msg.text, msg.lang)
    except KeyboardInterrupt:
        pass
    finally:
        t.close()
    return 0 if got or a.count == 0 else 1


def bench_rows(mtu: int = 255) -> list[tuple[str, str, str, int, int, float]]:
    rows = []
    for lang in LANGUAGES:
        for kind, table in (("dict", PHRASES), ("held-out", SAMPLES)):
            for text in table[lang]:
                pkts = encode_message(text, lang, 0, mtu)
                utf8, total = len(text.encode("utf-8")), sum(map(len, pkts))
                rows.append((lang, kind, text, utf8, total, utf8 / total))
    return rows


def cmd_bench(a: argparse.Namespace) -> int:
    rows = bench_rows()
    print(f"{'lang':<5}{'set':<10}{'UTF-8 B':>8}{'packet B':>10}{'ratio':>7}  text")
    for lang, kind, text, utf8, total, ratio in rows:
        print(f"{lang:<5}{kind:<10}{utf8:>8}{total:>10}{ratio:>6.2f}x  {text}")
    print()
    for kind in ("dict", "held-out", "all"):
        sizes = [r[4] for r in rows if kind == "all" or r[1] == kind]
        under = sum(s <= 40 for s in sizes)
        print(f"{kind:<9} n={len(sizes):<3} packet bytes min/median/max = "
              f"{min(sizes)}/{statistics.median(sizes):g}/{max(sizes)}; <=40 B: {under}/{len(sizes)}")
    print("(packet bytes include the 6-byte header+CRC; 'dict' phrases seed the compression "
          "dictionary, 'held-out' do not)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="vaanisetu", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="encode text and send it over UDP")
    s.add_argument("text")
    s.add_argument("--lang", default="en", choices=LANGUAGES)
    s.add_argument("--to", default=DEFAULT_ADDR)
    s.add_argument("--mtu", type=int, default=DEFAULT_MTU)
    s.add_argument("--msg-id", type=int, default=0)
    s.add_argument("--repeat", type=int, default=1, help="send everything N times (loss cover)")
    s.set_defaults(fn=cmd_send)
    r = sub.add_parser("receive", help="listen on UDP and print received messages")
    r.add_argument("--bind", default=DEFAULT_ADDR)
    r.add_argument("--count", type=int, default=0, help="exit after N messages (0 = forever)")
    r.add_argument("--timeout", type=float, default=0.0, help="exit after N idle seconds")
    r.set_defaults(fn=cmd_receive)
    b = sub.add_parser("bench", help="measure real packet sizes of bundled sentences")
    b.set_defaults(fn=cmd_bench)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
