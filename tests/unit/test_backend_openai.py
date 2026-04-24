"""OpenAI TTS backend tests (mocked client)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.tts.openai import OpenAIBackend


class _FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def stream_to_file(self, path: str) -> None:
        from pathlib import Path as PathLib
        PathLib(path).write_bytes(self._data)


@pytest.mark.asyncio
async def test_synthesize_writes_output(tmp_path: Path) -> None:
    out = tmp_path / "o.mp3"
    create = AsyncMock()
    create.return_value = _FakeStream(b"ID3xxxxxx")
    client = MagicMock()
    client.audio = MagicMock()
    client.audio.speech = MagicMock()
    client.audio.speech.with_streaming_response = MagicMock()
    client.audio.speech.with_streaming_response.create = create

    with patch("app.backends.tts.openai.AsyncOpenAI", return_value=client):
        backend = OpenAIBackend(api_key="sk-test")
        result = await backend.synthesize(
            "hi",
            voice="nova",
            model="gpt-4o-mini-tts",
            output_path=out,
            format="mp3",
            style="happy and slow",
        )

    assert out.read_bytes() == b"ID3xxxxxx"
    assert result.voice == "nova"
    assert result.model == "gpt-4o-mini-tts"
    _, kwargs = create.call_args
    assert kwargs["instructions"] == "happy and slow"
    assert kwargs["voice"] == "nova"
    assert kwargs["response_format"] == "mp3"


@pytest.mark.asyncio
async def test_style_omitted_when_blank(tmp_path: Path) -> None:
    out = tmp_path / "o.mp3"
    create = AsyncMock()
    create.return_value = _FakeStream(b"ID3")
    client = MagicMock()
    client.audio.speech.with_streaming_response.create = create

    with patch("app.backends.tts.openai.AsyncOpenAI", return_value=client):
        backend = OpenAIBackend(api_key="sk-test")
        await backend.synthesize(
            "hi", voice="alloy", model="", output_path=out, format="mp3", style=""
        )
    _, kwargs = create.call_args
    assert "instructions" not in kwargs or kwargs["instructions"] == ""
