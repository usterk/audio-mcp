"""`list_voices` MCP tool."""
from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from app.backends.tts.voices import for_backend

TtsBackend = Literal["piper", "gcloud", "openai", "gemini"]


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_voices(backend: TtsBackend) -> list[dict]:
        """Enumerate voices available for a TTS backend."""
        voices = for_backend(backend)
        if not voices:
            raise ValueError(f"unknown TTS backend: {backend!r}")
        return list(voices)
