"""Integration test: generate_audio tool + download endpoint."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _make_fake_request(app):
    """Build a minimal Starlette Request that carries the given app."""
    from starlette.requests import Request
    from starlette.types import Scope

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
async def test_generate_audio_piper_stub(
    client: TestClient, tmp_data_dir: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    # Also update the already-created settings object on the running app
    client.app.state.settings.public_base_url = "http://testserver"

    from app.backends.tts.base import TTSResult

    async def fake_synth(self, text, *, voice, model, output_path, format, style):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"ID3fake")
        return TTSResult(
            audio_path=output_path,
            duration_sec=1.0,
            bytes=7,
            voice=voice or self.default_voice,
            backend="piper",
            format=format,
        )

    # Set up the HTTP-request context var so get_http_request() succeeds
    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)

    try:
        with patch("app.backends.tts.piper.PiperBackend.synthesize", new=fake_synth):
            mcp = client.app.state.mcp
            response = await mcp.call_tool(
                "generate_audio",
                {"text": "Cześć FBI", "backend": "piper"},
            )
    finally:
        _current_http_request.reset(token)

    # call_tool returns a ToolResult; structured_content holds the dict
    assert response.structured_content is not None, (
        f"Expected structured_content, got: {response}"
    )
    result = response.structured_content

    assert result["backend"] == "piper"
    assert result["download"]["audio"].endswith(".mp3")
    assert "ef bi aj" in result["normalized_text"]

    uuid = result["uuid"]
    r = client.get(f"/jobs/{uuid}/audio.mp3")
    assert r.status_code == 200
    assert r.content == b"ID3fake"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generate_audio_returns_queued_when_prediction_exceeds_budget(
    client: TestClient, monkeypatch
) -> None:
    """When predicted time > wait_max_sec, return queued without blocking."""
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "http://testserver")
    client.app.state.settings.public_base_url = "http://testserver"

    # Force a giant prediction: prime stats with a high rate.
    client.app.state.stats.record(
        kind="generate_audio", backend="piper", model_key=None,
        size_proxy=1.0, processing_sec=10.0,  # 10 sec/char
    )

    import asyncio

    started = asyncio.Event()
    can_finish = asyncio.Event()

    from app.backends.tts.base import TTSResult

    async def slow_synth(self, text, *, voice, model, output_path, format, style):
        started.set()
        await can_finish.wait()  # block forever in this test
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"X")
        return TTSResult(
            audio_path=output_path, duration_sec=0.1, bytes=1,
            voice=voice or self.default_voice, backend="piper", format=format,
        )

    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)
    try:
        with patch("app.backends.tts.piper.PiperBackend.synthesize", new=slow_synth):
            long_text = "Dzień dobry świecie, to jest test. " * 20
            response = await client.app.state.mcp.call_tool(
                "generate_audio",
                {"text": long_text, "backend": "piper", "wait_max_sec": 1},
            )
            payload = response.structured_content
            # 100 chars * 10 sec/char = 1000s predicted, way over 1s budget.
            assert payload["was_async"] is True
            assert payload["status"] in ("queued", "running")
            assert payload["uuid"]
            assert payload["check_after_sec"] is not None
    finally:
        _current_http_request.reset(token)
        can_finish.set()  # release the background task so it doesn't leak
