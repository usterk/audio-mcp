"""Google Cloud TTS backend tests (mocked client)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.backends.tts.gcloud import GCloudBackend


@pytest.mark.asyncio
async def test_synthesizes_and_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "out.mp3"
    resp = MagicMock(audio_content=b"ID3xxxxxx")
    client = MagicMock()
    client.synthesize_speech.return_value = resp

    with patch("app.backends.tts.gcloud.tts.TextToSpeechClient", return_value=client):
        backend = GCloudBackend()
        result = await backend.synthesize(
            "Cześć",
            voice="pl-PL-Standard-A",
            model="",
            output_path=out,
            format="mp3",
            style="",
        )

    assert out.read_bytes() == b"ID3xxxxxx"
    assert result.backend == "gcloud"
    assert result.voice == "pl-PL-Standard-A"
    assert result.bytes == len(b"ID3xxxxxx")


@pytest.mark.asyncio
async def test_wav_uses_linear16(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"
    client = MagicMock()
    client.synthesize_speech.return_value = MagicMock(audio_content=b"RIFFx")

    with patch("app.backends.tts.gcloud.tts.TextToSpeechClient", return_value=client):
        backend = GCloudBackend()
        await backend.synthesize(
            "hi", voice="en-US-Standard-C", model="", output_path=out, format="wav", style=""
        )

    args, kwargs = client.synthesize_speech.call_args
    cfg = kwargs.get("audio_config") or args[2]
    assert cfg.audio_encoding.name == "LINEAR16"
