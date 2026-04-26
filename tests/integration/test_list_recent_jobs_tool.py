import pytest
from starlette.requests import Request
from starlette.types import Scope


def _make_fake_request(app) -> Request:
    """Build a minimal Starlette Request that carries the given app."""
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_returns_recent_jobs(client, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    client.app.state.settings.public_base_url = "http://testserver"

    await client.app.state.jobs_db.create_job(
        uuid="j1", kind="transcribe", backend="groq", params={}
    )

    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)

    try:
        result = await client.app.state.mcp.call_tool("list_recent_jobs", {"limit": 5})
    finally:
        _current_http_request.reset(token)

    jobs = result.structured_content["result"]
    assert any(r["uuid"] == "j1" for r in jobs)
    j1 = next(r for r in jobs if r["uuid"] == "j1")
    # New ETA-aware fields are present even on freshly-created jobs.
    assert "status" in j1
    assert "elapsed_sec" in j1
    assert "eta_remaining_sec" in j1
    assert "predicted_processing_sec" in j1
    assert "download" in j1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_running_job_has_queue_position(client, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    client.app.state.settings.public_base_url = "http://testserver"

    await client.app.state.jobs_db.create_job(
        uuid="run", kind="transcribe", backend="local", params={},
        size_proxy=300.0, predicted_processing_sec=75.0, model_key="small",
    )
    await client.app.state.jobs_db.mark_started("run")
    await client.app.state.job_queue.submit(
        uuid="run", sem_backend="faster_whisper", predicted_proc_sec=75.0
    )
    await client.app.state.job_queue.start("run")

    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)
    try:
        result = await client.app.state.mcp.call_tool("list_recent_jobs", {"limit": 5})
    finally:
        _current_http_request.reset(token)

    jobs = result.structured_content["result"]
    target = next(r for r in jobs if r["uuid"] == "run")
    assert target["status"] == "running"
    assert target["queue_position"] == 0
    assert target["predicted_wait_sec"] == pytest.approx(0.0)
    assert target["eta_remaining_sec"] is not None
