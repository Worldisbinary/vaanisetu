"""Speech adapters.

The packet/codec/transport core needs NO models. STT/TTS are pluggable interfaces:

* TextOnlySTT / TextOnlyTTS: always available; treat "audio" as UTF-8 text and print text.
* VoskSTT: optional offline STT (`pip install vosk` plus a downloaded model directory).
  Imported lazily, so importing this module never requires vosk.
* PlaceholderTTS: stub marking where an on-device TTS engine will plug in. It does not
  synthesize audio yet.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class STT(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes, lang: str) -> str: ...


class TTS(ABC):
    @abstractmethod
    def speak(self, text: str, lang: str) -> bytes | None:
        """Return audio bytes (or None if the backend plays/prints directly)."""


class TextOnlySTT(STT):
    def transcribe(self, audio: bytes, lang: str) -> str:
        return audio.decode("utf-8")


class TextOnlyTTS(TTS):
    def speak(self, text: str, lang: str) -> bytes | None:
        print(f"[{lang}] {text}")
        return None


class VoskSTT(STT):
    """Optional. Expects 16 kHz mono 16-bit PCM and a Vosk model directory for the language."""

    def __init__(self, model_path: str, sample_rate: int = 16000) -> None:
        try:
            import vosk  # lazy import
        except ImportError as e:  # pragma: no cover - depends on optional dep
            raise RuntimeError("VoskSTT needs `pip install vosk` and a model directory") from e
        self._vosk, self._rate = vosk, sample_rate
        self._model = vosk.Model(model_path)

    def transcribe(self, audio: bytes, lang: str) -> str:  # pragma: no cover
        import json

        rec = self._vosk.KaldiRecognizer(self._model, self._rate)
        rec.AcceptWaveform(audio)
        return json.loads(rec.FinalResult()).get("text", "")


class PlaceholderTTS(TTS):
    def speak(self, text: str, lang: str) -> bytes | None:
        raise NotImplementedError("on-device TTS backend is on the roadmap; use TextOnlyTTS")


def get_stt(name: str = "text", **kw) -> STT:
    if name == "text":
        return TextOnlySTT()
    if name == "vosk":
        return VoskSTT(**kw)
    raise ValueError(f"unknown STT backend {name!r}")


def get_tts(name: str = "text") -> TTS:
    if name == "text":
        return TextOnlyTTS()
    if name == "placeholder":
        return PlaceholderTTS()
    raise ValueError(f"unknown TTS backend {name!r}")
