"""Resolve a UUIDv4 to a previously uploaded file."""
from __future__ import annotations

import mimetypes
import re

from app.config import Settings
from app.resolver.types import ResolvedSource

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return ResolvedSource(
        source_type="upload",
        audio_path=path,
        content_type=content_type,
        cleanup_paths=[],
    )
