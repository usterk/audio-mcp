"""Unit tests for app.storage.files."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.storage.files import (
    output_path,
    remove_expired_uploads,
    upload_path,
    write_stream,
)


def test_upload_path_is_uuid_under_uploads(tmp_data_dir: Path) -> None:
    p = upload_path(tmp_data_dir, "11111111-1111-1111-1111-111111111111", "audio/mpeg")
    assert p.parent == tmp_data_dir / "uploads"
    assert p.suffix == ".mp3"


def test_output_path_extension_per_kind(tmp_data_dir: Path) -> None:
    j = output_path(tmp_data_dir, "abc", "transcription", "json")
    assert j == tmp_data_dir / "outputs" / "abc.json"
    mp3 = output_path(tmp_data_dir, "abc", "audio", "mp3")
    assert mp3 == tmp_data_dir / "outputs" / "abc.mp3"


@pytest.mark.asyncio
async def test_write_stream_writes_chunks(tmp_data_dir: Path) -> None:
    async def source():
        yield b"hello "
        yield b"world"

    target = tmp_data_dir / "uploads" / "test.bin"
    written = await write_stream(source(), target)
    assert written == len(b"hello world")
    assert target.read_bytes() == b"hello world"


def test_remove_expired_uploads_respects_ttl(tmp_data_dir: Path) -> None:
    uploads = tmp_data_dir / "uploads"
    old = uploads / "old.bin"
    new = uploads / "new.bin"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    old_time = time.time() - 10_000
    import os

    os.utime(old, (old_time, old_time))

    removed = remove_expired_uploads(tmp_data_dir, ttl_seconds=3_600)
    assert removed == 1
    assert not old.exists()
    assert new.exists()
