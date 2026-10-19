"""Binary packet format with CRC-16 and fragment reassembly.

Layout (big-endian, 6 bytes overhead):
  byte 0   version (3 bits) | codec method (1 bit) | language id (4 bits)
  byte 1   message id (0-255)
  byte 2   fragment index (4 bits) | fragment count - 1 (4 bits)
  byte 3   payload length (0-255)
  ...      payload
  last 2   CRC-16/CCITT-FALSE over all preceding bytes
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from .languages import LANGUAGES

VERSION = 1
HEADER_LEN = 4
CRC_LEN = 2
OVERHEAD = HEADER_LEN + CRC_LEN
MAX_FRAGMENTS = 16
MAX_PAYLOAD = 255


class PacketError(ValueError):
    pass


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class Packet:
    lang_id: int
    msg_id: int
    index: int
    count: int
    payload: bytes
    method: int = 0
    version: int = VERSION

    def encode(self) -> bytes:
        if self.version != VERSION:
            raise PacketError(f"unsupported version {self.version}")
        if not 0 <= self.lang_id < len(LANGUAGES):
            raise PacketError("bad language id")
        if self.method not in (0, 1):
            raise PacketError("bad codec method")
        if not 0 <= self.msg_id <= 255:
            raise PacketError("bad message id")
        if not 1 <= self.count <= MAX_FRAGMENTS or not 0 <= self.index < self.count:
            raise PacketError("bad fragment fields")
        if len(self.payload) > MAX_PAYLOAD:
            raise PacketError("payload too large")
        head = bytes([
            (self.version << 5) | (self.method << 4) | self.lang_id,
            self.msg_id,
            (self.index << 4) | (self.count - 1),
            len(self.payload),
        ])
        body = head + self.payload
        return body + crc16(body).to_bytes(2, "big")

    @staticmethod
    def decode(raw: bytes) -> Packet:
        if len(raw) < OVERHEAD:
            raise PacketError("packet too short")
        body, crc = raw[:-CRC_LEN], int.from_bytes(raw[-CRC_LEN:], "big")
        if crc16(body) != crc:
            raise PacketError("CRC mismatch")
        version, method, lang_id = raw[0] >> 5, (raw[0] >> 4) & 1, raw[0] & 0x0F
        if version != VERSION:
            raise PacketError(f"unsupported version {version}")
        if lang_id >= len(LANGUAGES):
            raise PacketError(f"unknown language id {lang_id}")
        index, count = raw[2] >> 4, (raw[2] & 0x0F) + 1
        if index >= count:
            raise PacketError("fragment index out of range")
        if raw[3] != len(raw) - OVERHEAD:
            raise PacketError("length field mismatch")
        return Packet(lang_id, raw[1], index, count, bytes(raw[HEADER_LEN:-CRC_LEN]), method, version)

    def __len__(self) -> int:
        return OVERHEAD + len(self.payload)


def fragment(lang_id: int, msg_id: int, method: int, data: bytes, mtu: int) -> list[Packet]:
    """Split `data` into packets of at most `mtu` bytes each (including overhead)."""
    room = min(mtu - OVERHEAD, MAX_PAYLOAD)
    if room < 1:
        raise PacketError(f"mtu {mtu} too small (overhead is {OVERHEAD})")
    chunks = [data[i:i + room] for i in range(0, len(data), room)] or [b""]
    if len(chunks) > MAX_FRAGMENTS:
        raise PacketError(f"message needs {len(chunks)} fragments, max {MAX_FRAGMENTS}")
    return [Packet(lang_id, msg_id, i, len(chunks), c, method) for i, c in enumerate(chunks)]


class Reassembler:
    """Collects fragments in any order; duplicates are ignored.

    Fragments identical to those of a recently completed message (last `memory` ids) are
    ignored too, so blind retransmission does not deliver a message twice. A new message
    reusing an id with different content is accepted as new.
    """

    def __init__(self, memory: int = 32) -> None:
        self._parts: dict[int, dict[int, Packet]] = {}
        self._done: OrderedDict[int, dict[int, bytes]] = OrderedDict()
        self._memory = memory

    def add(self, pkt: Packet) -> bytes | None:
        """Add a fragment. Returns the full payload when complete, else None."""
        done = self._done.get(pkt.msg_id)
        if done is not None and len(done) == pkt.count and done.get(pkt.index) == pkt.payload                 and pkt.msg_id not in self._parts:
            return None
        parts = self._parts.setdefault(pkt.msg_id, {})
        if parts:
            first = next(iter(parts.values()))
            if (first.count, first.lang_id, first.method) != (pkt.count, pkt.lang_id, pkt.method):
                raise PacketError("inconsistent fragments for message id")
        if pkt.index in parts:
            if parts[pkt.index].payload != pkt.payload:
                raise PacketError("conflicting duplicate fragment")
            return None
        parts[pkt.index] = pkt
        if len(parts) < pkt.count:
            return None
        del self._parts[pkt.msg_id]
        self._done[pkt.msg_id] = {i: p.payload for i, p in parts.items()}
        self._done.move_to_end(pkt.msg_id)
        while len(self._done) > self._memory:
            self._done.popitem(last=False)
        return b"".join(parts[i].payload for i in range(pkt.count))
