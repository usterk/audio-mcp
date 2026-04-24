"""Lazy backend registry shared by tools."""
from __future__ import annotations

from functools import cache

from app.backends.transcription.faster_whisper import FasterWhisperBackend
from app.backends.transcription.groq import GroqBackend
from app.config import Settings


@cache
def _faster_whisper() -> FasterWhisperBackend:
    return FasterWhisperBackend()


def get_transcription_backend(name: str, settings: Settings):
    if name == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured")
        return GroqBackend(api_key=settings.groq_api_key)
    if name == "local":
        return _faster_whisper()
    raise ValueError(f"unknown transcription backend: {name!r}")
