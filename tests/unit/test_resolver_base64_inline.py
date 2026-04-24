"""Tests for the base64 inline resolver."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from app.config import Settings
from app.resolver.base64_inline import try_base64


@pytest.mark.asyncio
async def test_valid_base64_is_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    settings = Settings()
    payload = b"\xff\xfbaudio"
    data_uri = "data:audio/mpeg;base64," + base64.b64encode(payload).decode()
    resolved = await try_base64(data_uri, settings=settings, work_dir=tmp_path)
    assert resolved is not None
    assert resolved.source_type == "base64"
    assert resolved.audio_path.read_bytes() == payload
    assert resolved.content_type == "audio/mpeg"
    assert resolved.audio_path in resolved.cleanup_paths


@pytest.mark.asyncio
async def test_non_data_uri_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    settings = Settings()
    resolved = await try_base64("not a data uri", settings=settings, work_dir=tmp_path)
    assert resolved is None


@pytest.mark.asyncio
async def test_oversize_rejects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUDIO_MCP_INLINE_B64_MAX_BYTES", "4")
    settings = Settings()
    data_uri = "data:audio/mpeg;base64," + base64.b64encode(b"xxxxxxx").decode()
    with pytest.raises(ValueError, match="inline base64 payload exceeds"):
        await try_base64(data_uri, settings=settings, work_dir=tmp_path)
