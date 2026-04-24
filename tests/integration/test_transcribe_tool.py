"""Integration test for the transcribe MCP tool (Phase 8)."""
from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.types import Scope

from app.backends.transcription.base import TranscriptionResult


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
async def test_transcribe_tool_end_to_end(
    client: TestClient, tmp_data_dir: Path
) -> None:
    """Upload a dummy WAV, call the transcribe tool, verify result + artefacts."""

    # ── 1. Upload a dummy audio file via HTTP ──────────────────────────────────
    r = client.post(
        "/upload",
        files={"file": ("test.wav", io.BytesIO(b"RIFFxxxxWAVEfmt "), "audio/wav")},
    )
    assert r.status_code == 200
    upload_id = r.json()["upload_id"]

    # ── 2. Prepare the mock Groq result ───────────────────────────────────────
    fake_result = TranscriptionResult(
        segments=[{"start": 0.0, "end": 1.0, "text": "hello"}],
        text="hello",
        duration=1.0,
        language="en",
        backend="groq",
        model="whisper-large-v3-turbo",
    )

    # ── 3. Set up the HTTP-request context var so get_http_request() succeeds ─
    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)

    try:
        with patch(
            "app.backends.transcription.groq.GroqBackend.transcribe",
            new_callable=AsyncMock,
            return_value=fake_result,
        ):
            # Also need GROQ_API_KEY to be non-empty so backend is created
            client.app.state.settings.groq_api_key = "test-key"

            mcp = client.app.state.mcp
            tool_result = await mcp.call_tool(
                "transcribe",
                {"source": upload_id, "backend": "groq", "language": "en"},
            )
    finally:
        _current_http_request.reset(token)

    # ── 4. Inspect the tool result ────────────────────────────────────────────
    # call_tool returns a ToolResult; structured_content holds the dict
    assert tool_result.structured_content is not None, (
        f"Expected structured_content, got: {tool_result}"
    )
    result = tool_result.structured_content

    assert "uuid" in result
    assert "summary" in result
    assert result["segments_count"] == 1
    assert result["duration_sec"] == pytest.approx(1.0)
    assert result["language"] == "en"
    assert "download" in result
    assert "json" in result["download"]
    assert "txt" in result["download"]
    assert result["preview"] == "hello"

    job_uuid = result["uuid"]

    # ── 5. Verify artefacts were written to disk ───────────────────────────────
    json_file = tmp_data_dir / "outputs" / f"{job_uuid}.json"
    txt_file = tmp_data_dir / "outputs" / f"{job_uuid}.txt"
    assert json_file.exists(), f"JSON artefact missing: {json_file}"
    assert txt_file.exists(), f"TXT artefact missing: {txt_file}"

    stored = json.loads(json_file.read_text())
    assert stored["text"] == "hello"
    assert stored["language"] == "en"
    assert stored["backend"] == "groq"

    assert txt_file.read_text().strip() == "hello"

    # ── 6. Fetch artefacts via HTTP ───────────────────────────────────────────
    j_resp = client.get(f"/jobs/{job_uuid}/transcription.json")
    assert j_resp.status_code == 200
    assert j_resp.json()["text"] == "hello"

    t_resp = client.get(f"/jobs/{job_uuid}/transcription.txt")
    assert t_resp.status_code == 200
    assert t_resp.text.strip() == "hello"

    # ── 7. Job metadata should show status=done ───────────────────────────────
    meta = client.get(f"/jobs/{job_uuid}").json()
    assert meta["status"] == "done"
    assert meta["uuid"] == job_uuid
