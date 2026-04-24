"""Tests for upload_id resolver."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.resolver.upload_ref import try_upload_ref
from app.storage.files import upload_path


@pytest.mark.asyncio
async def test_returns_none_for_non_uuid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert await try_upload_ref("https://example.com", settings=settings) is None


@pytest.mark.asyncio
async def test_returns_none_for_unknown_uuid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    settings = Settings()
    settings.ensure_dirs()
    assert await try_upload_ref(
        "00000000-0000-0000-0000-000000000000", settings=settings
    ) is None


@pytest.mark.asyncio
async def test_finds_uploaded_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    settings = Settings()
    settings.ensure_dirs()
    uid = "11111111-1111-1111-1111-111111111111"
    p = upload_path(settings.data_dir, uid, "audio/wav")
    p.write_bytes(b"RIFF")

    resolved = await try_upload_ref(uid, settings=settings)
    assert resolved is not None
    assert resolved.source_type == "upload"
    assert resolved.audio_path == p
    assert resolved.content_type == "audio/wav"
    assert resolved.cleanup_paths == []
