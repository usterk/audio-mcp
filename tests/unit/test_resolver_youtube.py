"""YouTube resolver tests."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.resolver.youtube import extract_video_id, try_youtube


def test_extract_video_id_variants() -> None:
    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ&feature=share", "dQw4w9WgXcQ"),
    ]
    for url, expected in cases:
        assert extract_video_id(url) == expected


def test_extract_video_id_non_yt() -> None:
    assert extract_video_id("https://example.com/watch") is None


@pytest.mark.asyncio
async def test_non_youtube_returns_none(tmp_path: Path) -> None:
    resolved = await try_youtube(
        "https://example.com", work_dir=tmp_path, prefer_audio=False, languages=None
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_fast_path_uses_transcript_api(tmp_path: Path) -> None:
    fake_transcript = [
        {"text": "hello", "start": 0.0, "duration": 1.0},
        {"text": "world", "start": 1.0, "duration": 1.0},
    ]

    class FakeApi:
        @staticmethod
        def get_transcript(video_id: str, languages: list[str] | None = None) -> list[dict[str, Any]]:
            return fake_transcript

    with patch("app.resolver.youtube.YouTubeTranscriptApi", FakeApi):
        resolved = await try_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            work_dir=tmp_path,
            prefer_audio=False,
            languages=None,
        )
    assert resolved is not None
    assert resolved.source_type == "youtube_transcript"
    assert resolved.transcript_data is not None
    assert resolved.transcript_data["segments"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_audio_fallback_when_transcripts_unavailable(tmp_path: Path) -> None:
    class FakeApi:
        @staticmethod
        def get_transcript(video_id: str, languages: list[str] | None = None) -> list[dict[str, Any]]:
            raise RuntimeError("no transcripts")

    def fake_download(url: str, out_dir: Path) -> Path:
        p = out_dir / "audio.m4a"
        p.write_bytes(b"audio")
        return p

    with patch("app.resolver.youtube.YouTubeTranscriptApi", FakeApi), patch(
        "app.resolver.youtube._download_audio", side_effect=fake_download
    ):
        resolved = await try_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            work_dir=tmp_path,
            prefer_audio=False,
            languages=None,
        )
    assert resolved is not None
    assert resolved.source_type == "youtube_audio"
    assert resolved.audio_path.exists()
    assert resolved.audio_path in resolved.cleanup_paths


@pytest.mark.asyncio
async def test_prefer_audio_skips_transcript_fast_path(tmp_path: Path) -> None:
    def fake_download(url: str, out_dir: Path) -> Path:
        p = out_dir / "audio.m4a"
        p.write_bytes(b"audio")
        return p

    with patch("app.resolver.youtube._download_audio", side_effect=fake_download) as dl:
        resolved = await try_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            work_dir=tmp_path,
            prefer_audio=True,
            languages=None,
        )
    assert dl.called
    assert resolved is not None
    assert resolved.source_type == "youtube_audio"
