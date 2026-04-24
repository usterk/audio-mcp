"""Public preprocessing entry point."""
from __future__ import annotations

import re
from typing import Literal

from app.preprocessing.dictionaries import load
from app.preprocessing.rules import apply_rules

Mode = Literal["basic", "none"]


def normalize_text(text: str, *, language: str = "pl", mode: Mode = "basic") -> str:
    if mode == "none":
        return text
    out = apply_rules(text)
    mapping = load(language)
    if mapping:
        pattern = re.compile(
            r"(?<![A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])(" + "|".join(sorted(mapping, key=len, reverse=True)) + r")(?![A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż])"
        )

        def _sub(match: re.Match[str]) -> str:
            return mapping[match.group(1)]

        out = pattern.sub(_sub, out)
    return out
