"""HTTP(S) audio file downloader."""
from __future__ import annotations

import mimetypes
import uuid as uuidlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.resolver.types import ResolvedSource


async def try_http_url(source: str, *, work_dir: Path) -> ResolvedSource | None:
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"}:
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(parsed.path).suffix or ""
    target = work_dir / f"{uuidlib.uuid4()}{ext or '.bin'}"
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", source) as response:
            if response.status_code >= 400:
                raise ValueError(f"HTTP {response.status_code} while fetching {source}")
            content_type = response.headers.get("content-type", "").split(";")[0] or (
                mimetypes.guess_type(source)[0] or "application/octet-stream"
            )
            with target.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)

    return ResolvedSource(
        source_type="http_url",
        audio_path=target,
        content_type=content_type,
        cleanup_paths=[target],
    )
