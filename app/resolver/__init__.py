"""Resolve a `source` string into something we can transcribe."""
from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.resolver.base64_inline import try_base64
from app.resolver.http_url import try_http_url
from app.resolver.types import ResolvedSource
from app.resolver.upload_ref import try_upload_ref
from app.resolver.youtube import try_youtube


async def resolve_source(
    source: str,
    *,
    settings: Settings,
    work_dir: Path,
    prefer_audio: bool,
    languages: list[str] | None,
) -> ResolvedSource:
    resolvers = [
        lambda: try_base64(source, settings=settings, work_dir=work_dir),
        lambda: try_upload_ref(source, settings=settings),
        lambda: try_youtube(
            source, work_dir=work_dir, prefer_audio=prefer_audio, languages=languages
        ),
        lambda: try_http_url(source, work_dir=work_dir),
    ]
    for r in resolvers:
        resolved = await r()
        if resolved is not None:
            resolved.original_source = source
            return resolved
    raise ValueError(f"unrecognised source: {source!r}")
