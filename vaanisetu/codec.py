"""Text compression: NFC -> per-script 1-byte encoding -> optional deflate with preset dictionary.

Compact byte format (per language):
  0x00-0x7F  index into the language's alphabet (script block, or Urdu table)
  0x80-0xFE  ASCII character (byte - 0x80); ASCII 0x7F is escaped
  0xFF       escape: followed by the UTF-8 bytes of one arbitrary character

`encode` returns (method, data): method 0 = compact only, 1 = raw deflate over the
compact bytes using a preset dictionary built from that language's bundled phrases.
The smaller result wins (ties go to method 0). Round-trip is exact up to NFC.
"""

from __future__ import annotations

import unicodedata
import zlib
from functools import cache

from .languages import alphabet, check_lang
from .phrases import PHRASES

METHOD_COMPACT = 0
METHOD_DEFLATE = 1
MAX_DECODED = 4096  # guard against decompression bombs


class CodecError(ValueError):
    pass


@cache
def _tables(lang: str) -> tuple[str, dict[str, int]]:
    alpha = alphabet(lang)
    return alpha, {c: i for i, c in enumerate(alpha)}


def compact_encode(text: str, lang: str) -> bytes:
    check_lang(lang)
    _, index = _tables(lang)
    out = bytearray()
    for ch in unicodedata.normalize("NFC", text):
        i = index.get(ch)
        if i is not None:
            out.append(i)
        elif ord(ch) < 0x7F:
            out.append(0x80 | ord(ch))
        else:
            out.append(0xFF)
            out += ch.encode("utf-8", "surrogatepass")
    return bytes(out)


def compact_decode(data: bytes, lang: str) -> str:
    check_lang(lang)
    alpha, _ = _tables(lang)
    out: list[str] = []
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        i += 1
        if b < 0x80:
            if b >= len(alpha):
                raise CodecError(f"byte 0x{b:02x} not in alphabet for {lang}")
            out.append(alpha[b])
        elif b < 0xFF:
            out.append(chr(b & 0x7F))
        else:
            if i >= n:
                raise CodecError("truncated escape")
            lead = data[i]
            size = 1 if lead < 0x80 else 2 if lead >> 5 == 0b110 else 3 if lead >> 4 == 0b1110 \
                else 4 if lead >> 3 == 0b11110 else 0
            if size == 0 or i + size > n:
                raise CodecError("bad escaped character")
            try:
                out.append(data[i:i + size].decode("utf-8", "surrogatepass"))
            except UnicodeDecodeError as e:
                raise CodecError("bad escaped character") from e
            i += size
    return "".join(out)


@cache
def _zdict(lang: str) -> bytes:
    # Most frequent / most useful material goes last (closest to the data).
    return b"".join(compact_encode(p, lang) + b"\x80\xa0" for p in PHRASES.get(lang, []))[-32768:]


def _deflate(data: bytes, lang: str) -> bytes:
    zd = _zdict(lang)
    c = zlib.compressobj(9, zlib.DEFLATED, -15, 9, zlib.Z_DEFAULT_STRATEGY, zdict=zd) if zd \
        else zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def _inflate(data: bytes, lang: str) -> bytes:
    zd = _zdict(lang)
    d = zlib.decompressobj(-15, zdict=zd) if zd else zlib.decompressobj(-15)
    try:
        out = d.decompress(data, MAX_DECODED)
        if not d.eof or d.unconsumed_tail:
            raise CodecError("deflate stream incomplete or too large")
    except zlib.error as e:
        raise CodecError(f"deflate error: {e}") from e
    return out


def encode(text: str, lang: str) -> tuple[int, bytes]:
    """Compress `text`; returns (method, payload)."""
    compact = compact_encode(text, lang)
    packed = _deflate(compact, lang)
    if len(packed) < len(compact):
        return METHOD_DEFLATE, packed
    return METHOD_COMPACT, compact


def decode(method: int, data: bytes, lang: str) -> str:
    if method == METHOD_COMPACT:
        return compact_decode(data, lang)
    if method == METHOD_DEFLATE:
        return compact_decode(_inflate(data, lang), lang)
    raise CodecError(f"unknown codec method {method}")
