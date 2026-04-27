"""Tests for app.audio.compress."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.compress import compress_for_groq

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not available"
)


def _synth_wav(path: Path, *, seconds: float = 2.0, sample_rate: int = 16000) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={seconds}",
            "-ar", str(sample_rate),
            "-ac", "1",
            str(path),
        ],
        check=True,
    )


@pytest.mark.asyncio
async def test_compresses_to_opus_16k_mono(tmp_path: Path) -> None:
    src = tmp_path / "src.wav"
    _synth_wav(src, seconds=3.0, sample_rate=44100)

    out = await compress_for_groq(src, work_dir=tmp_path / "out")

    assert out.exists()
    assert out.stat().st_size > 0
    # Original WAV at 44.1k should be larger than compressed opus.
    assert out.stat().st_size < src.stat().st_size

    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=channels,codec_name",
            "-of", "default=noprint_wrappers=1",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # libopus normalises sample rate to 48 kHz at the container layer even when
    # we ask ffmpeg for 16 kHz, so we only assert codec + channel count here.
    assert "codec_name=opus" in probe
    assert "channels=1" in probe
