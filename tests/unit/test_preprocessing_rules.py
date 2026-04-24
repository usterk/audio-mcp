"""Preprocessing rule tests."""
from __future__ import annotations

from app.preprocessing.rules import apply_rules


def test_strips_http_urls() -> None:
    out = apply_rules("See https://example.com/path?x=1 for details.")
    assert "https://" not in out
    assert "example.com" not in out


def test_strips_long_hashes() -> None:
    sha = "a" * 40
    out = apply_rules(f"commit {sha} is broken")
    assert sha not in out


def test_keeps_short_alnum() -> None:
    out = apply_rules("room 404 upstairs")
    assert "404" in out


def test_markdown_fences_removed() -> None:
    text = "Before\n```\ncode\n```\nAfter"
    out = apply_rules(text)
    assert "```" not in out
    assert "code" not in out


def test_emphasis_markers_removed() -> None:
    out = apply_rules("This is **bold** and _italic_")
    assert "**" not in out
    assert "_" not in out
    assert "bold" in out
    assert "italic" in out


def test_whitespace_normalised() -> None:
    out = apply_rules("a\n\n\nb      c")
    assert "  " not in out
    assert "a b c" in out.replace("\n", " ")
