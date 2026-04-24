"""HTTP URL resolver tests."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from app.resolver.http_url import try_http_url


@pytest.mark.asyncio
async def test_non_http_returns_none(tmp_path: Path) -> None:
    assert await try_http_url("file:///etc/hosts", work_dir=tmp_path) is None


@pytest.mark.asyncio
@respx.mock
async def test_downloads_audio_file(tmp_path: Path) -> None:
    url = "https://example.com/a.mp3"
    respx.get(url).mock(
        return_value=httpx.Response(
            200, content=b"\xff\xfbxxxx", headers={"content-type": "audio/mpeg"}
        )
    )
    resolved = await try_http_url(url, work_dir=tmp_path)
    assert resolved is not None
    assert resolved.source_type == "http_url"
    assert resolved.audio_path.exists()
    assert resolved.audio_path.read_bytes() == b"\xff\xfbxxxx"
    assert resolved.content_type == "audio/mpeg"
    assert resolved.audio_path in resolved.cleanup_paths


@pytest.mark.asyncio
@respx.mock
async def test_raises_on_http_error(tmp_path: Path) -> None:
    url = "https://example.com/missing.mp3"
    respx.get(url).mock(return_value=httpx.Response(404))
    with pytest.raises(ValueError, match="HTTP 404"):
        await try_http_url(url, work_dir=tmp_path)
