"""Groq-hosted Whisper adapter."""
from __future__ import annotations

from pathlib import Path

from groq import AsyncGroq

from app.audio.chunk import AudioChunk, chunk_audio
from app.backends.transcription.base import TranscriptionResult
from app.config import Settings
from app.logging_setup import get_logger

DEFAULT_MODEL = "whisper-large-v3-turbo"


def _segment_from_response(s, idx: int, *, offset: float = 0.0) -> dict:
    if isinstance(s, dict):
        return {
            "id": s.get("id", idx),
            "start": float(s.get("start", 0.0)) + offset,
            "end": float(s.get("end", 0.0)) + offset,
            "text": s.get("text", ""),
        }
    return {
        "id": getattr(s, "id", idx),
        "start": float(s.start) + offset,
        "end": float(s.end) + offset,
        "text": s.text,
    }


class GroqBackend:
    name = "groq"

    def __init__(self, *, api_key: str, settings: Settings | None = None) -> None:
        self._api_key = api_key
        self._settings = settings

    async def _call_api(
        self, audio_path: Path, *, language: str | None, model_id: str
    ):
        client = AsyncGroq(api_key=self._api_key)
        with audio_path.open("rb") as fh:
            return await client.audio.transcriptions.create(
                file=(audio_path.name, fh),
                model=model_id,
                response_format="verbose_json",
                language=language or None,
            )

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        model: str | None,
    ) -> TranscriptionResult:
        model_id = model or DEFAULT_MODEL
        max_bytes = (
            self._settings.groq_max_request_bytes if self._settings else 24 * 1024 * 1024
        )
        chunk_seconds = (
            self._settings.groq_chunk_seconds if self._settings else 600
        )
        size = audio_path.stat().st_size
        if size <= max_bytes:
            response = await self._call_api(
                audio_path, language=language, model_id=model_id
            )
            segments_raw = getattr(response, "segments", None) or []
            return TranscriptionResult(
                segments=[
                    _segment_from_response(s, i) for i, s in enumerate(segments_raw)
                ],
                text=getattr(response, "text", "") or "",
                duration=float(getattr(response, "duration", 0.0) or 0.0),
                language=getattr(response, "language", "") or "",
                backend="groq",
                model=model_id,
            )

        log = get_logger(__name__)
        chunks: list[AudioChunk] = await chunk_audio(
            audio_path,
            chunk_seconds=chunk_seconds,
            work_dir=audio_path.parent / f"{audio_path.stem}.chunks",
        )
        log.info(
            "chunked_groq",
            chunks=len(chunks),
            chunk_seconds=chunk_seconds,
            size_bytes=size,
        )

        merged_segments: list[dict] = []
        merged_text_parts: list[str] = []
        merged_duration = 0.0
        merged_language = ""
        next_id = 0
        for chunk in chunks:
            response = await self._call_api(
                chunk.path, language=language, model_id=model_id
            )
            for seg in getattr(response, "segments", None) or []:
                merged_segments.append(
                    _segment_from_response(seg, next_id, offset=chunk.offset_sec)
                )
                next_id += 1
            chunk_text = getattr(response, "text", "") or ""
            if chunk_text:
                merged_text_parts.append(chunk_text)
            merged_duration = max(
                merged_duration,
                chunk.offset_sec + float(getattr(response, "duration", 0.0) or 0.0),
            )
            if not merged_language:
                merged_language = getattr(response, "language", "") or ""

        return TranscriptionResult(
            segments=merged_segments,
            text=" ".join(merged_text_parts),
            duration=merged_duration,
            language=merged_language,
            backend="groq",
            model=model_id,
        )
