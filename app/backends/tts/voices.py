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


def for_backend(backend: str) -> list[VoiceInfo]:
    return {
        "piper": PIPER,
        "gcloud": GCLOUD,
        "openai": OPENAI,
    }.get(backend, [])
