"""FastMCP server factory and shared instructions."""
from __future__ import annotations

from fastmcp import FastMCP

from app.tools import generate_audio as generate_audio_tool
from app.tools import get_job as get_job_tool
from app.tools import list_recent_jobs as list_recent_jobs_tool
from app.tools import list_voices as list_voices_tool
from app.tools import transcribe as transcribe_tool

INSTRUCTIONS = """\
audio-mcp — remote MCP server for audio transcription and text-to-speech.

Tools:
- transcribe(source, backend='groq', language='', model='', wait_max_sec=None)
  source may be: a YouTube URL, an HTTP(S) URL to an audio file,
  an inline "data:audio/...;base64,..." payload (<= 10 MB), or a UUID
  returned by POST /upload. For larger files, first POST the bytes to
  `{base_url}/upload`, then call `transcribe` with source = upload_id.
- generate_audio(text, backend='piper', voice='', normalize='basic', wait_max_sec=None, ...)
  Produces an MP3 by default; see list_voices(backend) for per-backend
  voice catalogues. Polish text is normalized with a rule-based
  preprocessor (URLs stripped, acronyms respelled) unless normalize='none'.

Soft cap (wait_max_sec, default 50 s): if the server predicts the job
will take longer than this budget, it returns immediately with status
`queued`/`running`, the job UUID, an `eta_remaining_sec`, and a
`check_after_sec` hint. Poll `get_job(uuid)` after that delay to fetch
the final result.

Long audio is handled automatically — do NOT pre-process it yourself.
For YouTube the server tries captions first (with retry on transient
errors), otherwise downloads the audio, re-encodes it to opus 16 kHz
mono ~24 kbps, and chunks it when it would exceed the cloud request-
size limit. If Groq still rejects the request, the call falls back to
the local CPU backend by default; ``notes`` in the response records
what happened. Use ``backend='local'`` only when you specifically want
CPU/off-cloud processing.

On failure the ``error`` field is a JSON object with ``message``,
``stage``, and ``next_steps`` — read those before retrying.

Helper tools:
- get_job(uuid) — current status, ETA, and download URLs for a single job.
- list_voices(backend) — enumerates voices for a backend.
- list_recent_jobs(limit=10) — overview of recent jobs with ETA fields.

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
    generate_audio_tool.register(mcp)
    list_voices_tool.register(mcp)
    list_recent_jobs_tool.register(mcp)
    get_job_tool.register(mcp)
    return mcp
