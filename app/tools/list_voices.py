"""`list_voices` MCP tool."""
from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from app.backends.tts.voices import for_backend
from app.tools._schemas import Voice

TtsBackend = Literal["piper", "gcloud", "openai", "gemini"]


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def list_voices(backend: TtsBackend) -> list[Voice]:
        """Enumerate voices available for a TTS backend."""
        voices = for_backend(backend)
        if not voices:
            raise ValueError(f"unknown TTS backend: {backend!r}")
        return [Voice.model_validate(v) for v in voices]
