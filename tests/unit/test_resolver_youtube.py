"""YouTube resolver tests."""
from __future__ import annotations

from pathlib import Path
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


class _FakeSnippet:
    """Minimal stand-in for youtube_transcript_api.FetchedTranscriptSnippet."""

    def __init__(self, text: str, start: float, duration: float) -> None:
        self.text = text
        self.start = start
        self.duration = duration


class _FakeFetched(list):
    """Iterable like FetchedTranscript with a .language_code attr."""

    def __init__(self, items: list[_FakeSnippet], language_code: str = "pl") -> None:
        super().__init__(items)
        self.language_code = language_code


@pytest.mark.asyncio
async def test_fast_path_uses_transcript_api(tmp_path: Path) -> None:
    fake_fetched = _FakeFetched(
        [_FakeSnippet("hello", 0.0, 1.0), _FakeSnippet("world", 1.0, 1.0)],
        language_code="pl",
    )

    class FakeApiInstance:
        def fetch(self, video_id: str, languages=None, preserve_formatting: bool = False):
            return fake_fetched

        def list(self, video_id: str):
            return iter([])

    with patch("app.resolver.youtube.YouTubeTranscriptApi", return_value=FakeApiInstance()):
        resolved = await try_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            work_dir=tmp_path,
            prefer_audio=False,
            languages=["pl"],
        )
    assert resolved is not None
    assert resolved.source_type == "youtube_transcript"
    assert resolved.transcript_data is not None
    assert resolved.transcript_data["segments"][0]["text"] == "hello"
    assert resolved.transcript_data["language"] == "pl"
    assert resolved.transcript_data["duration"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_fast_path_no_languages_picks_first_available(tmp_path: Path) -> None:
    fake_fetched = _FakeFetched(
        [_FakeSnippet("auto", 0.0, 1.5)], language_code="en"
    )

    class FakeTranscriptEntry:
        def fetch(self):
            return fake_fetched

    class FakeApiInstance:
        def fetch(self, video_id: str, languages=None, preserve_formatting: bool = False):
            raise RuntimeError("requires languages")

        def list(self, video_id: str):
            return iter([FakeTranscriptEntry()])

    with patch("app.resolver.youtube.YouTubeTranscriptApi", return_value=FakeApiInstance()):
        resolved = await try_youtube(
            "https://youtu.be/dQw4w9WgXcQ",
            work_dir=tmp_path,
            prefer_audio=False,
            languages=None,
        )
    assert resolved is not None
    assert resolved.source_type == "youtube_transcript"
    assert resolved.transcript_data["language"] == "en"


@pytest.mark.asyncio
async def test_audio_fallback_when_transcripts_unavailable(tmp_path: Path) -> None:
    class FakeApiInstance:
        def fetch(self, video_id: str, languages=None, preserve_formatting: bool = False):
            raise RuntimeError("no transcripts")

        def list(self, video_id: str):
            raise RuntimeError("no transcripts")

    def fake_download(url: str, out_dir: Path) -> Path:
        p = out_dir / "audio.m4a"
        p.write_bytes(b"audio")
        return p

    with patch("app.resolver.youtube.YouTubeTranscriptApi", return_value=FakeApiInstance()), patch(
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
