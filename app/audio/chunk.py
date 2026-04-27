"""Split long audio into ffmpeg-cut chunks for sequential cloud transcription."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AudioChunk:
    path: Path
    offset_sec: float


def _ffprobe_duration_sync(path: Path) -> float:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe not found on PATH")
    out = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


async def probe_duration(path: Path) -> float:
    return await asyncio.to_thread(_ffprobe_duration_sync, path)


def _cut_sync(src: Path, offset: float, length: float, dst: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel", "error",
            "-ss", f"{offset:.3f}",
            "-i", str(src),
            "-t", f"{length:.3f}",
            "-vn",
            "-c:a", "copy",
            str(dst),
        ],
        check=True,
    )


async def chunk_audio(
    src: Path, *, chunk_seconds: float, work_dir: Path
) -> list[AudioChunk]:
    """Cut ``src`` into ~``chunk_seconds`` long pieces under ``work_dir``.

    Uses ``-c copy`` to avoid re-encoding (cheap, lossless). Caller must
    ensure ``src`` is in a container that allows stream copy at arbitrary
    offsets — for our pipeline that's opus-in-ogg coming out of
    ``compress_for_groq``.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    duration = await probe_duration(src)
    if duration <= 0:
        raise RuntimeError(f"could not determine duration of {src}")

    chunks: list[AudioChunk] = []
    idx = 0
    offset = 0.0
    while offset < duration - 0.05:
        length = min(chunk_seconds, duration - offset)
        dst = work_dir / f"{src.stem}.part{idx:03d}{src.suffix}"
        await asyncio.to_thread(_cut_sync, src, offset, length, dst)
        chunks.append(AudioChunk(path=dst, offset_sec=offset))
        offset += length
        idx += 1
    return chunks
