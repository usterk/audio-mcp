"""GET / — minimal landing page."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>audio-mcp</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto;">
<h1>audio-mcp</h1>
<p>Remote MCP server for audio transcription and text-to-speech.</p>
<p>MCP endpoint: <code>POST /mcp</code></p>
<p>HTTP helpers: <code>POST /upload</code>, <code>GET /jobs/{uuid}/...</code>, <code>GET /health</code>.</p>
<p>Read the agent usage guide by calling the <code>usage_guide()</code> tool
or fetching the <code>audio-mcp://docs/usage</code> resource.</p>
</body></html>
"""


@router.get("/", response_class=HTMLResponse)
async def landing() -> str:
    return _HTML
