"""Resolve a UUIDv4 to a previously uploaded file."""
from __future__ import annotations

import mimetypes
import re

from app.config import Settings
from app.resolver.types import ResolvedSource

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Normalise platform-variant MIME types to canonical values.
_CANONICAL_MIME = {
    "audio/x-wav": "audio/wav",
    "audio/x-m4a": "audio/mp4",
    "audio/mp3": "audio/mpeg",
}


async def try_upload_ref(source: str, *, settings: Settings) -> ResolvedSource | None:
    if not _UUID_RE.match(source.strip()):
        return None
    uploads = settings.data_dir / "uploads"
    if not uploads.is_dir():
        return None
    candidates = list(uploads.glob(f"{source}.*"))
    if not candidates:
        return None
    path = candidates[0]
    raw_ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    content_type = _CANONICAL_MIME.get(raw_ct, raw_ct)
    return ResolvedSource(
        source_type="upload",
        audio_path=path,
        content_type=content_type,
        cleanup_paths=[],
    )
