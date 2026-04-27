"""Groq transcription backend tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.audio.chunk import AudioChunk
from app.backends.transcription.groq import GroqBackend
from app.config import Settings


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


@pytest.mark.asyncio
async def test_chunks_when_file_exceeds_limit(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "long.opus"
    audio.write_bytes(b"x" * (5 * 1024 * 1024))  # 5 MB stub

    settings = Settings(
        AUDIO_MCP_GROQ_MAX_REQUEST_BYTES=1 * 1024 * 1024,  # force chunking
        AUDIO_MCP_GROQ_CHUNK_SECONDS=10,
    )

    chunk_paths = [tmp_path / f"part{i}.opus" for i in range(3)]
    for p in chunk_paths:
        p.write_bytes(b"x")

    fake_chunks = [
        AudioChunk(path=chunk_paths[0], offset_sec=0.0),
        AudioChunk(path=chunk_paths[1], offset_sec=10.0),
        AudioChunk(path=chunk_paths[2], offset_sec=20.0),
    ]

    async def fake_chunk_audio(src, *, chunk_seconds, work_dir):
        return fake_chunks

    monkeypatch.setattr(
        "app.backends.transcription.groq.chunk_audio", fake_chunk_audio
    )

    responses = [
        MagicMock(
            text=f"part{i}",
            language="pl",
            duration=10.0,
            segments=[
                {"id": 0, "start": 0.0, "end": 5.0, "text": f"a{i}"},
                {"id": 1, "start": 5.0, "end": 10.0, "text": f"b{i}"},
            ],
        )
        for i in range(3)
    ]

    class _SeqClient:
        def __init__(self) -> None:
            self.audio = MagicMock()
            self.audio.transcriptions = MagicMock()
            self.audio.transcriptions.create = AsyncMock(side_effect=responses)

    with patch("app.backends.transcription.groq.AsyncGroq") as cls:
        cls.return_value = _SeqClient()
        backend = GroqBackend(api_key="gsk_test", settings=settings)
        result = await backend.transcribe(audio, language="pl", model=None)

    assert result.backend == "groq"
    assert result.language == "pl"
    assert result.duration == pytest.approx(30.0)
    starts = [seg["start"] for seg in result.segments]
    assert starts == [0.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    assert result.text == "part0 part1 part2"
