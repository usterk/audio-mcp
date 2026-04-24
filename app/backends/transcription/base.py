"""Protocol + result type for transcription backends."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class TranscriptionResult:
    segments: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""
    duration: float = 0.0
    language: str = ""
    backend: str = ""
    model: str = ""
    raw: dict[str, Any] | None = None


class TranscriptionBackend(Protocol):
    name: str

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        model: str | None,
    ) -> TranscriptionResult: ...
