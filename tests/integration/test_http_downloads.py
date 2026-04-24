"""Download endpoint tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_jobs_metadata_and_file_downloads(client: TestClient, tmp_data_dir: Path) -> None:
    # Seed a completed transcription job directly in the DB and on disk.
    jobs_db = client.app.state.jobs_db
    uuid = "11111111-1111-1111-1111-111111111111"
    await jobs_db.create_job(
        uuid=uuid,
        kind="transcribe",
        backend="groq",
        params={"source": "https://example.com/a.mp3"},
    )
    (tmp_data_dir / "outputs" / f"{uuid}.json").write_text(json.dumps({"segments": []}))
    (tmp_data_dir / "outputs" / f"{uuid}.txt").write_text("hello world")
    await jobs_db.mark_done(uuid, result={"duration_sec": 1.2})

    meta = client.get(f"/jobs/{uuid}").json()
    assert meta["uuid"] == uuid
    assert meta["status"] == "done"

    j = client.get(f"/jobs/{uuid}/transcription.json")
    assert j.status_code == 200
    assert j.json() == {"segments": []}

    t = client.get(f"/jobs/{uuid}/transcription.txt")
    assert t.status_code == 200
    assert t.text == "hello world"


def test_missing_job_404(client: TestClient) -> None:
    r = client.get("/jobs/99999999-9999-9999-9999-999999999999")
    assert r.status_code == 404


def test_audio_download_by_ext(client: TestClient, tmp_data_dir: Path) -> None:
    import asyncio

    async def seed():
        uuid = "22222222-2222-2222-2222-222222222222"
        await client.app.state.jobs_db.create_job(
            uuid=uuid, kind="generate_audio", backend="piper", params={}
        )
        (tmp_data_dir / "outputs" / f"{uuid}.mp3").write_bytes(b"\xff\xfbxxxx")
        await client.app.state.jobs_db.mark_done(uuid, result={"bytes": 6})
        return uuid

    uuid = asyncio.get_event_loop().run_until_complete(seed())
    r = client.get(f"/jobs/{uuid}/audio.mp3")
    assert r.status_code == 200
    assert r.content == b"\xff\xfbxxxx"
