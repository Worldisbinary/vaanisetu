"""Language table: ids, names and the 1-byte alphabets used by the codec."""

from __future__ import annotations

# Order defines the 4-bit language id carried in the packet header. Never reorder.
LANGUAGES: tuple[str, ...] = ("en", "hi", "bn", "te", "mr", "ta", "ur", "gu", "kn", "ml", "pa")

NAMES = {
    "en": "English", "hi": "Hindi", "bn": "Bengali", "te": "Telugu", "mr": "Marathi",
    "ta": "Tamil", "ur": "Urdu", "gu": "Gujarati", "kn": "Kannada", "ml": "Malayalam",
    "pa": "Punjabi",
}

# First code point of each script's 128-wide Unicode block.
_BLOCK_BASE = {
    "hi": 0x0900, "mr": 0x0900, "bn": 0x0980, "pa": 0x0A00, "gu": 0x0A80,
    "ta": 0x0B80, "te": 0x0C00, "kn": 0x0C80, "ml": 0x0D00,
}


def _urdu_alphabet() -> str:
    cps = [0x060C, 0x061B, 0x061F]
    cps += range(0x0621, 0x063B)
    cps += range(0x0640, 0x0653)
    cps += range(0x0660, 0x066A)
    cps += [0x0679, 0x067E, 0x0686, 0x0688, 0x0691, 0x0698, 0x06A9, 0x06AF, 0x06BA,
            0x06BE, 0x06C1, 0x06C3, 0x06CC, 0x06D2, 0x06D4]
    cps += range(0x06F0, 0x06FA)
    return "".join(chr(c) for c in cps)


def alphabet(lang: str) -> str:
    """Characters that cost 1 byte for `lang` (at most 127), besides ASCII."""
    check_lang(lang)
    if lang == "ur":
        return _urdu_alphabet()
    if lang in _BLOCK_BASE:
        base = _BLOCK_BASE[lang]
        return "".join(chr(base + i) for i in range(128))
    return ""


def check_lang(lang: str) -> None:
    if lang not in LANGUAGES:
        raise ValueError(f"unsupported language {lang!r}; expected one of {LANGUAGES}")


def lang_id(lang: str) -> int:
    check_lang(lang)
    return LANGUAGES.index(lang)


def lang_from_id(i: int) -> str:
    if not 0 <= i < len(LANGUAGES):
        raise ValueError(f"unknown language id {i}")
    return LANGUAGES[i]
