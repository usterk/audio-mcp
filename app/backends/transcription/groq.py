"""Groq-hosted Whisper adapter."""
from __future__ import annotations

from pathlib import Path

from groq import AsyncGroq

from app.backends.transcription.base import TranscriptionResult

DEFAULT_MODEL = "whisper-large-v3-turbo"


class GroqBackend:
    name = "groq"

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        model: str | None,
    ) -> TranscriptionResult:
        client = AsyncGroq(api_key=self._api_key)
        model_id = model or DEFAULT_MODEL
        with audio_path.open("rb") as fh:
            response = await client.audio.transcriptions.create(
                file=(audio_path.name, fh),
                model=model_id,
                response_format="verbose_json",
                language=language or None,
            )
        segments = getattr(response, "segments", None) or []
        return TranscriptionResult(
            segments=[
                {
                    "id": s.get("id", i) if isinstance(s, dict) else i,
                    "start": s["start"] if isinstance(s, dict) else s.start,
                    "end": s["end"] if isinstance(s, dict) else s.end,
                    "text": s["text"] if isinstance(s, dict) else s.text,
                }
                for i, s in enumerate(segments)
            ],
            text=getattr(response, "text", "") or "",
            duration=float(getattr(response, "duration", 0.0) or 0.0),
            language=getattr(response, "language", "") or "",
            backend="groq",
            model=model_id,
        )
