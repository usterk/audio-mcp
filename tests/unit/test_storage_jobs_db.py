"""Unit tests for app.storage.jobs_db."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.storage.jobs_db import JobsDB


@pytest.mark.asyncio
async def test_create_and_fetch_job(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(
        uuid="abc",
        kind="transcribe",
        backend="groq",
        params={"source": "https://example.com/audio.mp3"},
    )
    row = await db.get_job("abc")
    assert row is not None
    assert row["uuid"] == "abc"
    assert row["kind"] == "transcribe"
    assert row["status"] == "running"
    assert json.loads(row["params_json"]) == {"source": "https://example.com/audio.mp3"}


@pytest.mark.asyncio
async def test_mark_done_updates_result(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="x", kind="generate_audio", backend="piper", params={})
    await db.mark_done("x", result={"duration_sec": 1.5})
    row = await db.get_job("x")
    assert row["status"] == "done"
    assert json.loads(row["result_json"]) == {"duration_sec": 1.5}
    assert row["finished_at"] is not None


@pytest.mark.asyncio
async def test_mark_failed_stores_error(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="y", kind="transcribe", backend="groq", params={})
    await db.mark_failed("y", error="boom")
    row = await db.get_job("y")
    assert row["status"] == "failed"
    assert row["error"] == "boom"


@pytest.mark.asyncio
async def test_list_recent_returns_latest_first(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    for i in range(3):
        await db.create_job(uuid=f"u{i}", kind="transcribe", backend="groq", params={"i": i})
        await asyncio.sleep(1.1)  # Ensure distinct timestamps (> 1 second)
    rows = await db.list_recent(limit=2)
    assert [r["uuid"] for r in rows] == ["u2", "u1"]


@pytest.mark.asyncio
async def test_upload_records(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_upload(
        upload_id="up1",
        size_bytes=42,
        content_type="audio/mpeg",
        ttl_seconds=3_600,
    )
    row = await db.get_upload("up1")
    assert row is not None
    assert row["size_bytes"] == 42
    assert row["expires_at"] > row["created_at"]
