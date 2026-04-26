"""Static voice catalogues per backend."""
from __future__ import annotations

from typing import TypedDict


class VoiceInfo(TypedDict):
    id: str
    name: str
    language: str
    gender: str
    tags: list[str]


PIPER: list[VoiceInfo] = [
    {
        "id": "gosia-medium",
        "name": "Gosia (medium)",
        "language": "pl",
        "gender": "female",
        "tags": ["local", "cpu", "polish"],
    },
]

GCLOUD: list[VoiceInfo] = [
    {
        "id": "pl-PL-Standard-A",
        "name": "pl-PL-Standard-A",
        "language": "pl",
        "gender": "female",
        "tags": ["cloud", "cheap"],
    },
    {
        "id": "pl-PL-Standard-B",
        "name": "pl-PL-Standard-B",
        "language": "pl",
        "gender": "male",
        "tags": ["cloud", "cheap"],
    },
    {
        "id": "en-US-Standard-C",
        "name": "en-US-Standard-C",
        "language": "en",
        "gender": "female",
        "tags": ["cloud", "cheap"],
    },
]

OPENAI: list[VoiceInfo] = [
    {"id": "alloy", "name": "Alloy", "language": "en", "gender": "neutral", "tags": ["cloud", "style"]},
    {"id": "ash", "name": "Ash", "language": "en", "gender": "male", "tags": ["cloud", "style"]},
    {"id": "ballad", "name": "Ballad", "language": "en", "gender": "male", "tags": ["cloud", "style"]},
    {"id": "coral", "name": "Coral", "language": "en", "gender": "female", "tags": ["cloud", "style"]},
    {"id": "echo", "name": "Echo", "language": "en", "gender": "male", "tags": ["cloud", "style"]},
    {"id": "fable", "name": "Fable", "language": "en", "gender": "male", "tags": ["cloud", "style"]},
    {"id": "nova", "name": "Nova", "language": "en", "gender": "female", "tags": ["cloud", "style"]},
    {"id": "onyx", "name": "Onyx", "language": "en", "gender": "male", "tags": ["cloud", "style"]},
    {"id": "sage", "name": "Sage", "language": "en", "gender": "female", "tags": ["cloud", "style"]},
    {"id": "shimmer", "name": "Shimmer", "language": "en", "gender": "female", "tags": ["cloud", "style"]},
]

GEMINI: list[VoiceInfo] = [
    {"id": "Charon", "name": "Charon", "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Kore",   "name": "Kore",   "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Puck",   "name": "Puck",   "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Aoede",  "name": "Aoede",  "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Fenrir", "name": "Fenrir", "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Leda",   "name": "Leda",   "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Orus",   "name": "Orus",   "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Zephyr", "name": "Zephyr", "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
]


def for_backend(backend: str) -> list[VoiceInfo]:
    return {
        "piper": PIPER,
        "gcloud": GCLOUD,
        "openai": OPENAI,
        "gemini": GEMINI,
    }.get(backend, [])
