# audio-mcp

MCP server for audio processing — transcription and text-to-speech — deployed to a private home-lab
server (Aurora) and accessible over a Tailscale VPN from any client (Claude Desktop, Claude Code,
Gemini CLI, mobile agents).

Status: **design phase**. See [the design doc](docs/superpowers/specs/2026-04-24-audio-mcp-design.md)
for the v1.0 specification.

## Quick overview

Two MCP tools plus an HTTP API:

- `transcribe(source, backend, ...)` — YouTube URL, remote audio URL, base64 payload, or `upload_id`.
  Backends: `groq` (cloud, default) and `faster-whisper` (CPU local).
- `generate_audio(text, backend, voice, ...)` — TTS with text preprocessing for Polish.
  Backends: `piper` (local CPU, default, free), `gcloud` (Google Cloud TTS Standard),
  `openai` (`gpt-4o-mini-tts`).

Large file uploads, job metadata, and final downloads go through an HTTP API alongside the MCP
endpoint. Everything is served over HTTPS via a Tailscale sidecar container at
`https://audio-mcp.<tailnet>.ts.net`.

See [docs/superpowers/specs/2026-04-24-audio-mcp-design.md](docs/superpowers/specs/2026-04-24-audio-mcp-design.md).
