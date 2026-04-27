"""FastMCP server factory and shared instructions."""
from __future__ import annotations

from fastmcp import FastMCP

from app.tools import generate_audio as generate_audio_tool
from app.tools import get_job as get_job_tool
from app.tools import list_recent_jobs as list_recent_jobs_tool
from app.tools import list_voices as list_voices_tool
from app.tools import transcribe as transcribe_tool

INSTRUCTIONS = """\
audio-mcp — transcribe audio files (uploads, URLs, YouTube) to text
and synthesise audio files from text.

transcribe(source, mode='fast'|'offline')
  source = YouTube URL, audio URL, upload_id from POST /upload, or
  data:audio/...;base64,... payload. Long / large inputs are handled
  internally; do not pre-download or split them yourself.

generate_audio(text, backend, voice='')
  voice='' picks a sensible default for the language. Call
  list_voices(backend) only when the user named a specific voice.

Helpers: get_job(uuid), list_voices(backend), list_recent_jobs(limit).

If a job won't finish within the soft cap, the response is
status='queued' with a UUID and check_after_sec — poll get_job(uuid).
On a final failure, error.next_steps is the actionable playbook.

Companion HTTP: POST /upload (field 'file') → upload_id;
GET /jobs/{uuid}/transcription.{json,txt} or /audio.{mp3,wav,opus}.
"""


def create_mcp() -> FastMCP:
    mcp = FastMCP(name="audio-mcp", instructions=INSTRUCTIONS)
    transcribe_tool.register(mcp)
    generate_audio_tool.register(mcp)
    list_voices_tool.register(mcp)
    list_recent_jobs_tool.register(mcp)
    get_job_tool.register(mcp)
    return mcp
