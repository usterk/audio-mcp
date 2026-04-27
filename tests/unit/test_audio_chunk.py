"""Tests for app.audio.chunk."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.chunk import chunk_audio, probe_duration

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not available",
)


def _synth_opus(path: Path, *, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={seconds}",
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "libopus",
            "-b:a", "24k",
            str(path),
        ],
        check=True,
    )


@pytest.mark.asyncio
async def test_probe_duration_returns_seconds(tmp_path: Path) -> None:
    src = tmp_path / "speech.opus"
    _synth_opus(src, seconds=4.5)
    duration = await probe_duration(src)
    assert duration == pytest.approx(4.5, abs=0.2)


@pytest.mark.asyncio
async def test_chunk_audio_emits_offsets(tmp_path: Path) -> None:
    src = tmp_path / "long.opus"
    _synth_opus(src, seconds=10.0)
    chunks = await chunk_audio(src, chunk_seconds=4.0, work_dir=tmp_path / "chunks")
    assert len(chunks) == 3
    assert [round(c.offset_sec, 2) for c in chunks] == [0.0, 4.0, 8.0]
    for c in chunks:
        assert c.path.exists()
        assert c.path.stat().st_size > 0
