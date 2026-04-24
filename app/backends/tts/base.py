"""Protocol + result type for TTS backends."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Format = Literal["mp3", "wav", "opus"]


@dataclass
class TTSResult:
    audio_path: Path
    duration_sec: float
    bytes: int
    voice: str
    backend: str
    model: str = ""
    format: Format = "mp3"


class TTSBackend(Protocol):
    name: str
    default_voice: str
    normalizes_own_text: bool

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        model: str,
        output_path: Path,
        format: Format,
        style: str,
    ) -> TTSResult: ...
