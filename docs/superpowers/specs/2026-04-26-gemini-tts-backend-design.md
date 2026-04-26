# Gemini TTS Backend — Design Spec

**Date:** 2026-04-26
**Status:** Approved

## Overview

Add `gemini` as a fourth TTS backend in audio-mcp, using the Gemini 2.5 Flash TTS model
(`gemini-2.5-flash-preview-tts`) via direct REST calls. Gemini TTS is ~10× cheaper than
OpenAI TTS, supports Polish well, and is already proven in the FlowOS project.

## Motivation

- Price: ~$0.0001/thousand characters vs OpenAI ~$0.015/thousand words
- Quality: `gemini-2.5-flash-preview-tts` produces natural-sounding Polish speech
- No new library dependency: uses `httpx` which is already a project dependency

## Reference Implementation

`/Users/usterk/src/FlowOS/backend/app/plugins/clients/gemini_tts_client.py` — exact API
call pattern, PCM→WAV conversion, error handling.

## Architecture

### New file: `app/backends/tts/gemini.py`

`GeminiBackend` class implementing the `TTSBackend` Protocol:

```
name = "gemini"
default_voice = "Charon"
normalizes_own_text = True   # capable model, handles punctuation/acronyms itself
```

**`synthesize(text, *, voice, model, output_path, format, style) -> TTSResult`**

1. POST to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}`
2. Request body:
   ```json
   {
     "contents": [{"parts": [{"text": "..."}], "role": "user"}],
     "generationConfig": {
       "response_modalities": ["AUDIO"],
       "speech_config": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Charon"}}}
     }
   }
   ```
3. Response: base64-encoded raw PCM `audio/L16;rate=24000`
4. Decode PCM → wrap in WAV header (`_pcm_to_wav`, identical to FlowOS)
5. Format `wav` → write WAV directly to `output_path`
6. Format `mp3`/`opus` → write WAV to tempfile, convert via ffmpeg (same pattern as `PiperBackend`)
7. Duration: `len(pcm_bytes) / (sample_rate * 2)` seconds
8. `style` parameter ignored (Gemini TTS has no equivalent)
9. `model` defaults to `"gemini-2.5-flash-preview-tts"` if empty
10. Fully async — uses `asyncio.to_thread` is NOT needed since `httpx.AsyncClient` is natively async

**httpx usage:** Create a fresh `httpx.AsyncClient` per call (stateless, no connection pooling needed at this concurrency level). Timeout: 60s (TTS for long texts can be slow).

### Changes to existing files

**`app/backends/tts/voices.py`** — add `GEMINI` list:

```python
GEMINI: list[VoiceInfo] = [
    {"id": "Charon", "name": "Charon", "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Kore",   "name": "Kore",   "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Puck",   "name": "Puck",   "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Aoede",  "name": "Aoede",  "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Fenrir", "name": "Fenrir", "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Leda",   "name": "Leda",   "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
    {"id": "Orus",   "name": "Orus",   "language": "mul", "gender": "male",   "tags": ["cloud", "cheap"]},
    {"id": "Zephyr", "name": "Zephyr", "language": "mul", "gender": "female", "tags": ["cloud", "cheap"]},
]
```

Update `for_backend()` to include `"gemini": GEMINI`.

**`app/config.py`** — add:
```python
gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
```

**`app/backends/__init__.py`** — add to `get_tts_backend()`:
```python
if name == "gemini":
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY not set; cannot use the gemini TTS backend")
    return GeminiBackend(api_key=settings.gemini_api_key)
```

**`infra-poziomka/inventories/production/group_vars/poziomka/apps.yml`** — add to `audio-mcp.app_env_vars`:
```yaml
GEMINI_API_KEY: "{{ vault_app_secrets['audio-mcp'].GEMINI_API_KEY }}"
```

### `generate_audio` tool

No changes needed — `gemini` becomes a valid backend value. Update `VALID_BACKENDS` tuple:
```python
VALID_BACKENDS = ("piper", "gcloud", "openai", "gemini")
```

## Data Flow

```
generate_audio(text="...", backend="gemini", voice="Charon")
  → normalize_text() skipped (normalizes_own_text=True)
  → GeminiBackend.synthesize()
    → httpx POST → Gemini API
    → base64 decode → PCM bytes
    → _pcm_to_wav() → WAV bytes
    → write output_path (wav) or ffmpeg convert (mp3/opus)
  → TTSResult(duration_sec, bytes, voice, backend="gemini")
  → job marked done, download URL returned
```

## Testing

**`tests/unit/test_backend_gemini.py`** — two tests:
1. `test_synthesize_writes_wav_output` — mock `httpx.AsyncClient.post`, verify WAV written, duration calculated
2. `test_mp3_output_converts_via_ffmpeg` — mock httpx + subprocess, verify ffmpeg called

Mock response structure matches actual Gemini API response (base64 PCM, MIME type with rate).

## Error Handling

- Missing `GEMINI_API_KEY` → `ValueError` at factory time (before job created)
- HTTP error from Gemini API → `httpx.HTTPStatusError` propagates, job marked failed
- Empty candidates/parts in response → `ValueError("No audio in Gemini TTS response")`
- ffmpeg failure → `subprocess.CalledProcessError`, job marked failed

## Not in scope

- Streaming audio output (Gemini supports it but adds complexity; batch is sufficient)
- `style` / instruction parameter (no Gemini TTS equivalent)
- Caching or connection pooling for the HTTP client
- Adding Gemini as default backend (piper remains default)
