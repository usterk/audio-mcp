"""Dictionary-aware preprocessing tests."""
from __future__ import annotations

from app.preprocessing import normalize_text


def test_replaces_polish_acronym() -> None:
    out = normalize_text("Wiadomości dotarły do FBI wczoraj.", language="pl")
    assert "ef bi aj" in out
    assert "FBI" not in out


def test_does_not_touch_words_inside_other_words() -> None:
    out = normalize_text("unikalne słowo jesieńcia", language="pl")
    assert out == "unikalne słowo jesieńcia"


def test_mode_none_is_passthrough() -> None:
    out = normalize_text("Sprawdź https://x.pl link i FBI", language="pl", mode="none")
    assert out == "Sprawdź https://x.pl link i FBI"


def test_unknown_language_no_crash() -> None:
    assert normalize_text("FBI to skrót", language="xx") != ""
