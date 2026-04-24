"""`list_voices` MCP tool."""
from __future__ import annotations

from fastmcp import FastMCP

from app.backends.tts.voices import for_backend


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_voices(backend: str) -> list[dict]:
        """Enumerate voices available for a TTS backend.

        Valid backends: ``piper``, ``gcloud``, ``openai``.
        """
        voices = for_backend(backend)
        if not voices:
            raise ValueError(f"unknown TTS backend: {backend!r}")
        return list(voices)
