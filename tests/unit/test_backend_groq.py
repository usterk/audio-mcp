"""Groq transcription backend tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.transcription.groq import GroqBackend


class _FakeAudio:
    def __init__(self, response) -> None:
        self._response = response
        self.transcriptions = MagicMock()
        self.transcriptions.create = AsyncMock(return_value=response)


class _FakeClient:
    def __init__(self, response) -> None:
        self.audio = _FakeAudio(response)


@pytest.mark.asyncio
async def test_returns_segments(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    fake_response = MagicMock()
    fake_response.text = "hello world"
    fake_response.language = "en"
    fake_response.duration = 1.5
    fake_response.segments = [
        {"id": 0, "start": 0.0, "end": 0.5, "text": "hello"},
        {"id": 1, "start": 0.5, "end": 1.0, "text": "world"},
    ]

    with patch("app.backends.transcription.groq.AsyncGroq") as cls:
        cls.return_value = _FakeClient(fake_response)
        backend = GroqBackend(api_key="gsk_test")
        result = await backend.transcribe(audio, language=None, model=None)

    assert result.text == "hello world"
    assert result.language == "en"
    assert result.duration == 1.5
    assert result.segments[1]["text"] == "world"
    assert result.backend == "groq"
    assert result.model == "whisper-large-v3-turbo"


@pytest.mark.asyncio
async def test_honours_explicit_model(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    fake_response = MagicMock(text="hi", language="en", duration=1.0, segments=[])
    with patch("app.backends.transcription.groq.AsyncGroq") as cls:
        client = _FakeClient(fake_response)
        cls.return_value = client
        backend = GroqBackend(api_key="gsk_test")
        await backend.transcribe(audio, language=None, model="whisper-large-v3")
    _, kwargs = client.audio.transcriptions.create.call_args
    assert kwargs["model"] == "whisper-large-v3"
