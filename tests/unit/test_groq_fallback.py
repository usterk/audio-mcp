"""Auto-fallback Groq → faster-whisper inside the transcribe tool."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp.exceptions import ToolError
from groq import APIStatusError

from app.backends.transcription.base import TranscriptionResult


def _make_fake_request(app):
    from starlette.requests import Request
    scope = {
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


def _groq_413() -> APIStatusError:
    response = httpx.Response(
        status_code=413,
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/audio/transcriptions"),
        content=b'{"error": {"message": "Request Entity Too Large", "code": "request_too_large"}}',
    )
    return APIStatusError(
        message="413 Request Entity Too Large",
        response=response,
        body={"error": {"message": "Request Entity Too Large"}},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_groq_413_falls_back_to_local(client: TestClient, tmp_data_dir: Path) -> None:
    r = client.post(
        "/upload",
        files={"file": ("test.wav", io.BytesIO(b"RIFFxxxxWAVEfmt "), "audio/wav")},
    )
    upload_id = r.json()["upload_id"]

    local_result = TranscriptionResult(
        segments=[{"start": 0.0, "end": 1.0, "text": "fell back"}],
        text="fell back",
        duration=1.0,
        language="en",
        backend="faster_whisper",
        model="small",
    )

    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)
    try:
        with patch(
            "app.tools.transcribe.compress_for_groq",
            new_callable=AsyncMock,
            side_effect=lambda src, work_dir: src,
        ), patch(
            "app.backends.transcription.groq.GroqBackend.transcribe",
            new_callable=AsyncMock,
            side_effect=_groq_413(),
        ), patch(
            "app.backends.transcription.faster_whisper.FasterWhisperBackend.transcribe",
            new_callable=AsyncMock,
            return_value=local_result,
        ):
            client.app.state.settings.groq_api_key = "test-key"
            mcp = client.app.state.mcp
            tool_result = await mcp.call_tool(
                "transcribe",
                {"source": upload_id, "backend": "groq", "language": "en"},
            )
    finally:
        _current_http_request.reset(token)

    payload = tool_result.structured_content
    assert payload["status"] == "done"
    assert payload["segments_count"] == 1
    assert payload["preview"] == "fell back"
    assert "notes" in payload
    assert any("falling back to local" in n for n in payload["notes"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_groq_413_raises_when_fallback_disabled(
    client: TestClient, tmp_data_dir: Path
) -> None:
    r = client.post(
        "/upload",
        files={"file": ("test.wav", io.BytesIO(b"RIFFxxxxWAVEfmt "), "audio/wav")},
    )
    upload_id = r.json()["upload_id"]

    from fastmcp.server.http import _current_http_request

    fake_request = _make_fake_request(client.app)
    token = _current_http_request.set(fake_request)
    try:
        with patch(
            "app.tools.transcribe.compress_for_groq",
            new_callable=AsyncMock,
            side_effect=lambda src, work_dir: src,
        ), patch(
            "app.backends.transcription.groq.GroqBackend.transcribe",
            new_callable=AsyncMock,
            side_effect=_groq_413(),
        ):
            client.app.state.settings.groq_api_key = "test-key"
            client.app.state.settings.groq_auto_fallback_local = False
            with pytest.raises(ToolError) as exc_info:
                await client.app.state.mcp.call_tool(
                    "transcribe",
                    {"source": upload_id, "backend": "groq"},
                )
            # The original cause should be the Groq APIStatusError, so the AI
            # caller can still tell the underlying problem from the error tail.
            assert "413" in str(exc_info.value)
            assert isinstance(exc_info.value.__cause__, APIStatusError)
    finally:
        _current_http_request.reset(token)
