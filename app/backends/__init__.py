"""Lazy backend registry shared by tools."""
from __future__ import annotations

from functools import cache

from app.backends.transcription.faster_whisper import FasterWhisperBackend
from app.backends.transcription.groq import GroqBackend
from app.backends.tts.gcloud import GCloudBackend
from app.backends.tts.gemini import GeminiBackend
from app.backends.tts.openai import OpenAIBackend
from app.backends.tts.piper import PiperBackend
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


def get_tts_backend(name: str, settings: Settings):
    if name == "piper":
        return PiperBackend(binary=settings.piper_binary, voice_dir=settings.piper_voice_dir)
    if name == "gcloud":
        if not settings.google_application_credentials:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS not set; cannot use the gcloud TTS backend"
            )
        return GCloudBackend()
    if name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set; cannot use the openai TTS backend")
        return OpenAIBackend(api_key=settings.openai_api_key)
    if name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set; cannot use the gemini TTS backend")
        return GeminiBackend(api_key=settings.gemini_api_key)
    raise ValueError(f"unknown TTS backend: {name!r}")
