"""Shared data types for source resolution."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SourceType = Literal["youtube_audio", "youtube_transcript", "http_url", "base64", "upload"]


@dataclass
class ResolvedSource:
    source_type: SourceType
    audio_path: Path | None = None
    original_source: str = ""
    transcript_data: dict[str, Any] | None = None  # only set for 'youtube_transcript'
    content_type: str = ""
    cleanup_paths: list[Path] = field(default_factory=list)
