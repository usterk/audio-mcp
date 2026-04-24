"""Register the audio-mcp://docs/usage resource."""
from __future__ import annotations

from fastmcp import FastMCP

from app.tools.usage_guide import _guide_text


def register(mcp: FastMCP) -> None:
    @mcp.resource("audio-mcp://docs/usage", mime_type="text/markdown")
    async def usage_resource() -> str:
        return _guide_text()
