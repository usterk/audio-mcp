"""GET / — minimal landing page."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.version import VERSION

router = APIRouter()

_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>audio-mcp</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 640px; margin: 2rem auto;">
<h1>audio-mcp</h1>
<p>Remote MCP server for audio transcription and text-to-speech.</p>
<p>MCP endpoint: <code>POST /mcp</code></p>
<p>HTTP helpers: <code>POST /upload</code>, <code>GET /jobs/{uuid}/...</code>, <code>GET /health</code>.</p>
<p>Agent usage guidance is delivered via the server-level MCP
<code>instructions</code> field and the <code>description</code> on each tool —
no separate guide tool to invoke.</p>
</body></html>
"""

_HTML = _HTML.replace(
    "</body></html>",
    f'<footer style="margin-top:2rem;font-size:12px;opacity:.5">'
    f"audio-mcp <code>v{VERSION}</code></footer>\n</body></html>",
)


@router.get("/", response_class=HTMLResponse)
async def landing() -> str:
    return _HTML
