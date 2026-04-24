# audio-mcp

Remote MCP server for audio processing, deployed to Aurora and reachable only over Tailscale.

## What it does

- **Transcribe** audio from YouTube URLs, HTTP(S) audio URLs, inline base64 payloads, or previously
  uploaded files. Backends: Groq Whisper (cloud, default) or local `faster-whisper` on CPU.
- **Generate audio** from text, with three backends: `piper` (local, free, Polish default voice),
  Google Cloud TTS Standard, OpenAI `gpt-4o-mini-tts`. Polish text is normalised (URLs and long
  hashes removed, acronyms respelled phonetically).
- **Job artefacts** (`transcription.json`, `transcription.txt`, `audio.mp3`) are downloadable via
  HTTP using URLs returned in each tool response.

## Connecting clients

All clients connect over Tailscale to `https://audio-mcp.uaru-teeth.ts.net/mcp`.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "audio-mcp": {
      "type": "http",
      "url": "https://audio-mcp.uaru-teeth.ts.net/mcp"
    }
  }
}
```

### Claude Code

Edit `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "audio-mcp": {
      "type": "http",
      "url": "https://audio-mcp.uaru-teeth.ts.net/mcp",
      "timeout": 900000
    }
  }
}
```

The raised `timeout` covers long CPU transcriptions.

## Development

```bash
uv sync
make dev           # run server locally
make test          # run tests with coverage
make lint          # ruff check
```

Requirements: Python 3.12, uv, ffmpeg.

## Architecture

- **FastAPI** + **FastMCP v3** — HTTP + MCP protocol
- **Groq** — cloud transcription (Whisper)
- **faster-whisper** — local CPU transcription
- **piper** — local TTS (Polish, free)
- **Google Cloud TTS** / **OpenAI TTS** — cloud TTS options
- **SQLite** (aiosqlite) — job and upload metadata
- **Tailscale** — secure network access
