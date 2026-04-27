"""Speech-friendly audio compression for cloud transcription.

Cloud backends (notably Groq Whisper) cap request size at ~25 MB. ffmpeg
re-encodes whatever yt-dlp / upload gave us into a tight opus-in-ogg
profile (16 kHz mono, ~24 kbps) that fits 60 min of speech in ~12 MB and
2 h in ~24 MB without audible degradation for transcription.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

from app.logging_setup import get_logger

OPUS_SAMPLE_RATE = 16000
OPUS_BITRATE = "24k"


def _compress_sync(src: Path, dst: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-i", str(src),
            "-vn",
            "-ac", "1",
            "-ar", str(OPUS_SAMPLE_RATE),
            "-c:a", "libopus",
            "-b:a", OPUS_BITRATE,
            str(dst),
        ],
        check=True,
    )


async def compress_for_groq(src: Path, *, work_dir: Path) -> Path:
    """Re-encode ``src`` into opus 16 kHz mono ~24 kbps under ``work_dir``.

    Returns the new path. The original file is left untouched so the caller
    decides whether to clean it up.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    dst = work_dir / f"{src.stem}.compressed.opus"
    log = get_logger(__name__)
    size_before = src.stat().st_size
    await asyncio.to_thread(_compress_sync, src, dst)
    size_after = dst.stat().st_size
    log.info(
        "compressed_for_groq",
        size_before=size_before,
        size_after=size_after,
        ratio=round(size_after / size_before, 3) if size_before else None,
        path=str(dst),
    )
    return dst
