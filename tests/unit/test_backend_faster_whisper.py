"""faster-whisper backend tests (mocked model)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.backends.transcription.faster_whisper import FasterWhisperBackend


def _fake_segments():
    seg_a = MagicMock(start=0.0, end=0.5, text="hello")
    seg_b = MagicMock(start=0.5, end=1.0, text="world")
    return iter([seg_a, seg_b])


@pytest.mark.asyncio
async def test_runs_with_mocked_model(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    fake_model = MagicMock()
    fake_info = MagicMock(language="pl", duration=1.0)
    fake_model.transcribe.return_value = (_fake_segments(), fake_info)

    with patch("app.backends.transcription.faster_whisper.WhisperModel", return_value=fake_model):
        backend = FasterWhisperBackend()
        result = await backend.transcribe(audio, language=None, model=None)

    assert result.backend == "faster_whisper"
    assert result.model == "small"
    assert result.language == "pl"
    assert result.duration == 1.0
    assert [s["text"] for s in result.segments] == ["hello", "world"]


@pytest.mark.asyncio
async def test_honours_explicit_model(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([]), MagicMock(language="en", duration=0.1))
    with patch("app.backends.transcription.faster_whisper.WhisperModel") as cls:
        cls.return_value = fake_model
        backend = FasterWhisperBackend()
        await backend.transcribe(audio, language="en", model="tiny")
        _, kwargs = cls.call_args
    assert kwargs["model_size_or_path"] == "tiny"
