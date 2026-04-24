"""faster-whisper (CTranslate2) CPU adapter."""
from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Lock

from faster_whisper import WhisperModel  # type: ignore[import-untyped]

from app.backends.transcription.base import TranscriptionResult

DEFAULT_MODEL = "small"


class FasterWhisperBackend:
    name = "faster_whisper"

    def __init__(self) -> None:
        self._cache: dict[str, WhisperModel] = {}
        self._lock = Lock()

    def _get_model(self, model_name: str) -> WhisperModel:
        with self._lock:
            if model_name not in self._cache:
                self._cache[model_name] = WhisperModel(
                    model_size_or_path=model_name, device="cpu", compute_type="int8"
                )
            return self._cache[model_name]

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        model: str | None,
    ) -> TranscriptionResult:
        model_name = model or DEFAULT_MODEL
        model_obj = self._get_model(model_name)

        def _run() -> TranscriptionResult:
            segments_iter, info = model_obj.transcribe(
                str(audio_path),
                language=language or None,
                vad_filter=True,
            )
            segments: list[dict] = []
            text_parts: list[str] = []
            for s in segments_iter:
                segments.append({"start": s.start, "end": s.end, "text": s.text})
                text_parts.append(s.text)
            return TranscriptionResult(
                segments=segments,
                text=" ".join(t.strip() for t in text_parts),
                duration=float(getattr(info, "duration", 0.0) or 0.0),
                language=getattr(info, "language", "") or "",
                backend="faster_whisper",
                model=model_name,
            )

        return await asyncio.to_thread(_run)
