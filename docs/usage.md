# audio-mcp usage guide

## Tools

### `transcribe(source, backend='groq', language='', model='')`

Accepts one of four forms of `source`:
1. A YouTube URL (transcript API fast path, audio fallback).
2. An HTTP(S) URL pointing directly at an audio file.
3. An inline base64 payload (`data:audio/...;base64,...`), up to 10 MB.
4. A UUID returned by `POST /upload` (for larger files).

Returns `{uuid, summary, duration_sec, language, segments_count, download: {json, txt}, preview}`.

### `generate_audio(text, backend='piper', voice='', model='', language='pl', normalize='basic', style='', format='mp3')`

Generates audio via piper (default, local), Google Cloud TTS Standard, or OpenAI `gpt-4o-mini-tts`.
By default Polish text is normalised: URLs stripped, long hashes stripped, common acronyms respelled
phonetically (`FBI` → `ef bi aj`). Returns `{uuid, duration_sec, bytes, voice, backend, model, format, download: {audio}, normalized_text}`.

## HTTP endpoints

- `POST /upload` — multipart upload, returns `{upload_id, size_bytes, content_type}`.
- `GET /uploads/{upload_id}` — metadata.
- `GET /jobs/{uuid}` — job metadata.
- `GET /jobs/{uuid}/transcription.json|txt` — downloads.
- `GET /jobs/{uuid}/audio.mp3|wav|opus` — downloads.

## End-to-end example (large file)

```bash
UPLOAD=$(curl -sS -F "file=@podcast.mp3" https://audio-mcp.<tailnet>.ts.net/upload | jq -r .upload_id)
# Then, in your MCP client, call: transcribe(source=$UPLOAD)
```

## Timeouts

Long transcriptions (CPU `local` backend) can take several minutes.
Raise the per-server timeout in your MCP client config, for example
`"timeout": 900000` (15 min) in `~/.claude/.mcp.json`.
