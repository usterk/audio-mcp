"""Load per-language acronym dictionaries."""
from __future__ import annotations

import json
from functools import cache
from importlib import resources


@cache
def load(language: str) -> dict[str, str]:
    try:
        path = resources.files("app.preprocessing.dictionaries").joinpath(f"{language}.json")
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
