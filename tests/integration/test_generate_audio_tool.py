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
