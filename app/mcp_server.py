"""FastMCP server factory and shared instructions."""
from __future__ import annotations

from fastmcp import FastMCP

from app.tools import transcribe as transcribe_tool

INSTRUCTIONS = """\
audio-mcp — remote MCP server for audio transcription and text-to-speech.

Tools:
- transcribe(source, backend='groq', language='', model='')
  source may be: a YouTube URL, an HTTP(S) URL to an audio file,
  an inline "data:audio/...;base64,..." payload (<= 10 MB), or a UUID
  returned by POST /upload. For larger files, first POST the bytes to
  `{base_url}/upload`, then call `transcribe` with source = upload_id.
- generate_audio(text, backend='piper', voice='', normalize='basic', ...)
  Produces an MP3 by default; see list_voices(backend) for per-backend
  voice catalogues. Polish text is normalized with a rule-based
  preprocessor (URLs stripped, acronyms respelled) unless normalize='none'.

Helper tools:
- list_voices(backend) — enumerates voices for a backend.
- list_recent_jobs(limit=10) — recovers results from recent sessions.
- usage_guide() — returns the full markdown guide (same content as the
  `audio-mcp://docs/usage` resource).

Companion HTTP API:
- POST /upload (multipart/form-data field 'file') → { upload_id }.
- GET  /jobs/{uuid}, /jobs/{uuid}/transcription.{json,txt},
       /jobs/{uuid}/audio.{mp3,wav,opus}.

Tool responses always include a `download` field with ready-made URLs
for any generated artefact. Use those URLs with standard HTTP — no extra
authentication is required within the tailnet.
"""


def create_mcp() -> FastMCP:
    mcp = FastMCP(name="audio-mcp", instructions=INSTRUCTIONS)
    transcribe_tool.register(mcp)
    return mcp
