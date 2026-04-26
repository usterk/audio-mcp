"""Verify the lifespan restart sweep marks orphaned jobs as failed."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import _sweep_unfinished_jobs, create_app
from app.storage.jobs_db import JobsDB


@pytest.mark.asyncio
async def test_sweep_marks_unfinished_as_failed(tmp_path):
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    await db.create_job(uuid="q", kind="transcribe", backend="groq", params={})
    await db.create_job(uuid="r", kind="transcribe", backend="groq", params={})
    await db.mark_started("r")
    await db.create_job(uuid="d", kind="transcribe", backend="groq", params={})
    await db.mark_done("d", result={})

    n = await _sweep_unfinished_jobs(db)
    assert n == 2

    rows = {r["uuid"]: r for r in await db.list_recent(limit=10)}
    assert rows["q"]["status"] == "failed"
    assert rows["q"]["error"] == "server_restart"
    assert rows["r"]["status"] == "failed"
    assert rows["r"]["error"] == "server_restart"
    assert rows["d"]["status"] == "done"


@pytest.mark.integration
def test_lifespan_runs_sweep_on_existing_db(tmp_data_dir, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_data_dir))

    # Pre-seed a 'running' row by writing it directly.
    import asyncio

    db = JobsDB(tmp_data_dir / "jobs.db")
    asyncio.run(db.init())

    async def _seed():
        await db.create_job(uuid="orphan", kind="transcribe", backend="groq", params={})
        await db.mark_started("orphan")

    asyncio.run(_seed())

    # Boot the app — lifespan should sweep.
    app = create_app()
    with TestClient(app) as client:
        async def _check():
            return await client.app.state.jobs_db.get_job("orphan")

        row = asyncio.run(_check())
        assert row["status"] == "failed"
        assert row["error"] == "server_restart"
