"""Unit tests for app.storage.jobs_db."""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from app.storage.jobs_db import JobsDB


@pytest.mark.asyncio
async def test_create_starts_queued(tmp_path: Path) -> None:
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
    assert row["status"] == "queued"
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert row["size_proxy"] is None
    assert json.loads(row["params_json"]) == {"source": "https://example.com/audio.mp3"}


@pytest.mark.asyncio
async def test_create_with_metadata(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(
        uuid="m",
        kind="generate_audio",
        backend="piper",
        params={"text": "hi"},
        size_proxy=2.0,
        predicted_processing_sec=0.04,
        model_key="gosia-medium",
    )
    row = await db.get_job("m")
    assert row["size_proxy"] == 2.0
    assert row["predicted_processing_sec"] == pytest.approx(0.04)
    assert row["model_key"] == "gosia-medium"


@pytest.mark.asyncio
async def test_mark_started_transitions_to_running(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="r", kind="transcribe", backend="groq", params={})
    await db.mark_started("r")
    row = await db.get_job("r")
    assert row["status"] == "running"
    assert row["started_at"] is not None


@pytest.mark.asyncio
async def test_update_size_proxy(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="s", kind="transcribe", backend="local", params={})
    await db.update_size_proxy("s", size_proxy=120.0, predicted_processing_sec=30.0)
    row = await db.get_job("s")
    assert row["size_proxy"] == 120.0
    assert row["predicted_processing_sec"] == 30.0


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
async def test_list_unfinished(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="q", kind="transcribe", backend="groq", params={})
    await db.create_job(uuid="r", kind="transcribe", backend="groq", params={})
    await db.mark_started("r")
    await db.create_job(uuid="d", kind="transcribe", backend="groq", params={})
    await db.mark_done("d", result={})
    await db.create_job(uuid="f", kind="transcribe", backend="groq", params={})
    await db.mark_failed("f", error="x")
    rows = await db.list_unfinished()
    uuids = {r["uuid"] for r in rows}
    assert uuids == {"q", "r"}


@pytest.mark.asyncio
async def test_query_recent_done_filters(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    # Eligible: kind=transcribe, backend=local, model_key='small', has size_proxy/started/finished
    await db.create_job(
        uuid="a",
        kind="transcribe",
        backend="local",
        params={},
        model_key="small",
    )
    await db.mark_started("a")
    await db.update_size_proxy("a", size_proxy=60.0)
    await db.mark_done("a", result={})
    # Wrong backend
    await db.create_job(
        uuid="b",
        kind="transcribe",
        backend="groq",
        params={},
        model_key="small",
    )
    await db.mark_started("b")
    await db.update_size_proxy("b", size_proxy=60.0)
    await db.mark_done("b", result={})
    # Failed
    await db.create_job(
        uuid="c",
        kind="transcribe",
        backend="local",
        params={},
        model_key="small",
    )
    await db.mark_started("c")
    await db.mark_failed("c", error="x")
    # Different model_key
    await db.create_job(
        uuid="d",
        kind="transcribe",
        backend="local",
        params={},
        model_key="large",
    )
    await db.mark_started("d")
    await db.update_size_proxy("d", size_proxy=60.0)
    await db.mark_done("d", result={})

    rows = await db.query_recent_done(
        kind="transcribe", backend="local", model_key="small", limit=10
    )
    assert [r for r in rows if r["size_proxy"] == 60.0]
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_query_recent_done_with_null_model_key(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="n", kind="transcribe", backend="groq", params={}, model_key=None)
    await db.mark_started("n")
    await db.update_size_proxy("n", size_proxy=10.0)
    await db.mark_done("n", result={})
    rows = await db.query_recent_done(
        kind="transcribe", backend="groq", model_key=None, limit=5
    )
    assert len(rows) == 1
    assert rows[0]["size_proxy"] == 10.0


@pytest.mark.asyncio
async def test_init_idempotent_and_migrates_legacy_db(tmp_path: Path) -> None:
    """Existing DB without new columns should get them via ALTER TABLE."""
    legacy_path = tmp_path / "legacy.db"
    # Simulate a pre-migration database (only original columns).
    conn = sqlite3.connect(legacy_path)
    conn.executescript(
        """
        CREATE TABLE jobs (
            uuid TEXT PRIMARY KEY, kind TEXT NOT NULL, backend TEXT NOT NULL,
            status TEXT NOT NULL, params_json TEXT NOT NULL, result_json TEXT,
            error TEXT, created_at INTEGER NOT NULL, finished_at INTEGER
        );
        INSERT INTO jobs (uuid, kind, backend, status, params_json, created_at)
        VALUES ('legacy', 'transcribe', 'groq', 'done', '{}', 1);
        """
    )
    conn.commit()
    conn.close()

    db = JobsDB(legacy_path)
    await db.init()
    # Re-init must not fail.
    await db.init()
    row = await db.get_job("legacy")
    assert row is not None
    # New columns now exist and default to NULL on legacy rows.
    assert row["started_at"] is None
    assert row["size_proxy"] is None
    assert row["predicted_processing_sec"] is None
    assert row["model_key"] is None


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
