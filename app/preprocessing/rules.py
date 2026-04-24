"""Regex-based preprocessing rules for TTS text."""
from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32,}\b|\b[A-Za-z0-9+/]{32,}={0,2}\b")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*\*|__)(.+?)\1")
_UNDERSCORE_EMPHASIS_RE = re.compile(r"(?<!\w)_(.+?)_(?!\w)")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")


def apply_rules(text: str) -> str:
    text = _CODE_FENCE_RE.sub(" ", text)
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _HEADER_RE.sub("", text)
    text = _EMPHASIS_RE.sub(lambda m: m.group(2), text)
    text = _UNDERSCORE_EMPHASIS_RE.sub(lambda m: m.group(1), text)
    text = _URL_RE.sub("", text)
    text = _HASH_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n", text)
    return text.strip()
