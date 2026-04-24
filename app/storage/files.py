"""File-system helpers for uploads and job outputs."""
from __future__ import annotations

import mimetypes
import time
from collections.abc import AsyncIterator
from pathlib import Path

# Canonical extension map for the content types we write.
_EXT_BY_MIME = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "audio/flac": ".flac",
    "audio/x-m4a": ".m4a",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/x-matroska": ".mkv",
}


def _extension_for(content_type: str) -> str:
    ext = _EXT_BY_MIME.get(content_type.lower())
    if ext:
        return ext
    guessed = mimetypes.guess_extension(content_type)
    return guessed or ".bin"


def upload_path(data_dir: Path, upload_id: str, content_type: str) -> Path:
    return data_dir / "uploads" / f"{upload_id}{_extension_for(content_type)}"


def output_path(data_dir: Path, uuid: str, kind: str, ext: str) -> Path:
    # kind is advisory (transcription/audio); the on-disk filename uses uuid + ext.
    _ = kind
    suffix = ext if ext.startswith(".") else f".{ext}"
    return data_dir / "outputs" / f"{uuid}{suffix}"


async def write_stream(source: AsyncIterator[bytes], target: Path) -> int:
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with target.open("wb") as fh:
        async for chunk in source:
            fh.write(chunk)
            total += len(chunk)
    return total


def remove_expired_uploads(data_dir: Path, *, ttl_seconds: int, now: float | None = None) -> int:
    now = now if now is not None else time.time()
    uploads = data_dir / "uploads"
    if not uploads.is_dir():
        return 0
    removed = 0
    for path in uploads.iterdir():
        if not path.is_file():
            continue
        age = now - path.stat().st_mtime
        if age > ttl_seconds:
            try:
                path.unlink()
                removed += 1
            except OSError:
                continue
    return removed
