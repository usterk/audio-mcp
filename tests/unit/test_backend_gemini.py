"""Gemini TTS backend tests (mocked httpx)."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.tts.gemini import GeminiBackend


def _fake_pcm(duration_sec: float = 1.0, sample_rate: int = 24000) -> bytes:
    """Generate dummy 16-bit mono PCM bytes for the given duration."""
    num_samples = int(sample_rate * duration_sec)
    return b"\x00\x01" * num_samples


def _fake_gemini_response(pcm_bytes: bytes, sample_rate: int = 24000) -> dict:
    """Build a minimal Gemini TTS API response dict."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": f"audio/L16;rate={sample_rate}",
                                "data": base64.b64encode(pcm_bytes).decode(),
                            }
                        }
                    ]
                }
            }
        ]
    }


def _make_mock_client(response_dict: dict) -> AsyncMock:
    """Return a mock httpx.AsyncClient context manager that returns response_dict."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_dict
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_synthesize_wav_output(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"
    pcm = _fake_pcm(1.0)

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client(_fake_gemini_response(pcm)),
    ):
        backend = GeminiBackend(api_key="test-key")
        result = await backend.synthesize(
            "Cześć",
            voice="Charon",
            model="",
            output_path=out,
            format="wav",
            style="",
        )

    assert out.exists()
    assert out.read_bytes()[:4] == b"RIFF"  # WAV header magic bytes
    assert result.voice == "Charon"
    assert result.backend == "gemini"
    assert result.model == "gemini-2.5-flash-preview-tts"
    assert result.duration_sec == pytest.approx(1.0, abs=0.01)
    assert result.format == "wav"


@pytest.mark.asyncio
async def test_mp3_output_converts_via_ffmpeg(tmp_path: Path) -> None:
    out = tmp_path / "out.mp3"
    pcm = _fake_pcm(0.5)

    ffmpeg_calls: list[list[str]] = []

    def fake_run(args, *, check):
        ffmpeg_calls.append(list(args))
        out.write_bytes(b"\xff\xfb" + b"\x00" * 100)  # fake MP3 bytes

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client(_fake_gemini_response(pcm)),
    ), patch("app.backends.tts.gemini.subprocess.run", side_effect=fake_run):
        backend = GeminiBackend(api_key="test-key")
        result = await backend.synthesize(
            "hello",
            voice="Kore",
            model="",
            output_path=out,
            format="mp3",
            style="",
        )

    assert any("ffmpeg" in " ".join(c) for c in ffmpeg_calls)
    assert any("libmp3lame" in c for call in ffmpeg_calls for c in call)
    assert result.format == "mp3"


@pytest.mark.asyncio
async def test_empty_candidates_raises(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client({"candidates": []}),
    ):
        backend = GeminiBackend(api_key="test-key")
        with pytest.raises(ValueError, match="No audio"):
            await backend.synthesize(
                "test", voice="", model="", output_path=out, format="wav", style=""
            )
