"""YouTube resolver — transcript fast path + yt-dlp audio fallback."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-untyped]

from app.resolver.types import ResolvedSource

_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"}
_SHORTS_RE = re.compile(r"/shorts/([A-Za-z0-9_-]{6,})")


def extract_video_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.hostname or ""
    if host not in _HOSTS:
        return None
    if host == "youtu.be":
        return parsed.path.lstrip("/") or None
    if parsed.path == "/watch":
        return parse_qs(parsed.query).get("v", [None])[0]
    m = _SHORTS_RE.match(parsed.path)
    if m:
        return m.group(1)
    return None


def _segments_from_transcript(raw: list[dict]) -> dict:
    segments = []
    full_text = []
    duration = 0.0
    for item in raw:
        segments.append(
            {
                "start": item["start"],
                "end": item["start"] + item["duration"],
                "text": item["text"],
            }
        )
        full_text.append(item["text"])
        duration = max(duration, item["start"] + item["duration"])
    return {
        "segments": segments,
        "text": " ".join(full_text),
        "duration": duration,
        "language": "",
    }


def _download_audio(url: str, out_dir: Path) -> Path:
    """yt-dlp wrapper, synchronous; call via asyncio.to_thread."""
    import subprocess

    out_dir.mkdir(parents=True, exist_ok=True)
    template = str(out_dir / "%(id)s.%(ext)s")
    subprocess.run(
        [
            "yt-dlp",
            "-f",
            "bestaudio[ext=m4a]/bestaudio",
            "-o",
            template,
            "--no-playlist",
            "--quiet",
            url,
        ],
        check=True,
    )
    files = sorted(out_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise RuntimeError("yt-dlp finished but produced no file")
    return files[0]


async def try_youtube(
    source: str,
    *,
    work_dir: Path,
    prefer_audio: bool,
    languages: list[str] | None,
) -> ResolvedSource | None:
    vid = extract_video_id(source)
    if vid is None:
        return None

    if not prefer_audio:
        try:
            raw = await asyncio.to_thread(
                YouTubeTranscriptApi.get_transcript, vid, languages=languages
            )
        except Exception:
            raw = None
        if raw:
            return ResolvedSource(
                source_type="youtube_transcript",
                audio_path=None,
                transcript_data=_segments_from_transcript(raw),
            )

    path = await asyncio.to_thread(_download_audio, source, work_dir)
    return ResolvedSource(
        source_type="youtube_audio",
        audio_path=path,
        content_type="audio/mp4",
        cleanup_paths=[path],
    )
