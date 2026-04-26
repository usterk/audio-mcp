"""Integration tests for the get_job MCP tool."""
from __future__ import annotations

import pytest
from starlette.requests import Request
from starlette.types import Scope


def _make_fake_request(app) -> Request:
    scope: Scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": [],
        "client": None,
        "server": None,
        "root_path": "",
        "app": app,
    }
    return Request(scope)


async def _call_get_job(client, uuid: str) -> dict:
    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)
    try:
        result = await client.app.state.mcp.call_tool("get_job", {"uuid": uuid})
    finally:
        _current_http_request.reset(token)
    return result.structured_content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_job_returns_done_job_with_result(client, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    client.app.state.settings.public_base_url = "http://testserver"

    await client.app.state.jobs_db.create_job(
        uuid="done-job", kind="transcribe", backend="groq", params={}
    )
    await client.app.state.jobs_db.mark_started("done-job")
    await client.app.state.jobs_db.update_size_proxy("done-job", size_proxy=60.0)
    await client.app.state.jobs_db.mark_done("done-job", result={"summary": "ok"})

    payload = await _call_get_job(client, "done-job")
    assert payload["uuid"] == "done-job"
    assert payload["status"] == "done"
    assert payload["eta_remaining_sec"] is None
    assert payload["check_after_sec"] is None
    assert payload["download"]["json"].endswith("/jobs/done-job/transcription.json")
    assert payload["result"] == {"summary": "ok"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_job_running_job_has_eta(client, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    client.app.state.settings.public_base_url = "http://testserver"

    await client.app.state.jobs_db.create_job(
        uuid="running-job",
        kind="transcribe",
        backend="local",
        params={},
        size_proxy=300.0,
        predicted_processing_sec=75.0,
        model_key="small",
    )
    await client.app.state.jobs_db.mark_started("running-job")
    # Register in the in-memory queue so snapshot returns position info
    await client.app.state.job_queue.submit(
        uuid="running-job", sem_backend="faster_whisper", predicted_proc_sec=75.0
    )
    await client.app.state.job_queue.start("running-job")

    payload = await _call_get_job(client, "running-job")
    assert payload["status"] == "running"
    assert payload["eta_remaining_sec"] is not None
    assert payload["eta_remaining_sec"] > 0
    assert payload["check_after_sec"] is not None
    assert payload["check_after_sec"] > payload["eta_remaining_sec"]
    assert payload["queue_position"] == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_job_unknown_uuid_raises(client):
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="Unknown job UUID"):
        await _call_get_job(client, "nope")
