# Gemini TTS Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gemini` as a fourth TTS backend using `gemini-2.5-flash-preview-tts` via direct REST (httpx), making it available in the `generate_audio` tool alongside piper, gcloud, and openai.

**Architecture:** `GeminiBackend` makes a POST to the Gemini generateContent endpoint, receives base64-encoded raw PCM (`audio/L16;rate=24000`), wraps it in a WAV header using a pure-Python helper, and optionally converts to mp3/opus via ffmpeg. The class implements the existing `TTSBackend` Protocol so it drops in to the current factory and tool without changes to the tool layer — only the factory and VALID_BACKENDS tuple need updating.

**Tech Stack:** Python 3.12, `httpx` (already a project dependency), `subprocess` + ffmpeg for format conversion, `struct` (stdlib) for WAV header, `base64` (stdlib) for PCM decode.

**Spec:** `docs/superpowers/specs/2026-04-26-gemini-tts-backend-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/backends/tts/gemini.py` | **Create** | `GeminiBackend` class + `_pcm_to_wav()` helper |
| `tests/unit/test_backend_gemini.py` | **Create** | Unit tests (mocked httpx) |
| `app/backends/tts/voices.py` | **Modify** | Add `GEMINI` voice list, update `for_backend()` |
| `app/config.py` | **Modify** | Add `gemini_api_key` field (`GEMINI_API_KEY`) |
| `app/backends/__init__.py` | **Modify** | Add `gemini` branch to `get_tts_backend()` |
| `app/tools/generate_audio.py` | **Modify** | Add `"gemini"` to `VALID_BACKENDS` |
| `infra-poziomka/inventories/production/group_vars/poziomka/apps.yml` | **Modify** | Add `GEMINI_API_KEY` env var for audio-mcp |

---

## Phase 1 — `GeminiBackend` (TDD)

### Task 1.1: Write failing tests

**Files:**
- Create: `tests/unit/test_backend_gemini.py`

- [ ] **Step 1: Create test file**

`tests/unit/test_backend_gemini.py`:

```python
"""Gemini TTS backend tests (mocked httpx)."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.backends.tts.gemini import GeminiBackend


def _fake_pcm(duration_sec: float = 1.0, sample_rate: int = 24000) -> bytes:
    """Generate dummy 16-bit mono PCM bytes for the given duration."""
    num_samples = int(sample_rate * duration_sec)
    return b"\x00\x01" * num_samples


def _fake_gemini_response(pcm_bytes: bytes, sample_rate: int = 24000) -> dict:
    """Build a minimal Gemini TTS API response dict."""
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": f"audio/L16;rate={sample_rate}",
                                "data": base64.b64encode(pcm_bytes).decode(),
                            }
                        }
                    ]
                }
            }
        ]
    }


def _make_mock_client(response_dict: dict) -> AsyncMock:
    """Return a mock httpx.AsyncClient context manager that returns response_dict."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_dict
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.mark.asyncio
async def test_synthesize_wav_output(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"
    pcm = _fake_pcm(1.0)

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client(_fake_gemini_response(pcm)),
    ):
        backend = GeminiBackend(api_key="test-key")
        result = await backend.synthesize(
            "Cześć",
            voice="Charon",
            model="",
            output_path=out,
            format="wav",
            style="",
        )

    assert out.exists()
    assert out.read_bytes()[:4] == b"RIFF"  # WAV header magic bytes
    assert result.voice == "Charon"
    assert result.backend == "gemini"
    assert result.model == "gemini-2.5-flash-preview-tts"
    assert result.duration_sec == pytest.approx(1.0, abs=0.01)
    assert result.format == "wav"


@pytest.mark.asyncio
async def test_mp3_output_converts_via_ffmpeg(tmp_path: Path) -> None:
    out = tmp_path / "out.mp3"
    pcm = _fake_pcm(0.5)

    ffmpeg_calls: list[list[str]] = []

    def fake_run(args, *, check):
        ffmpeg_calls.append(list(args))
        out.write_bytes(b"\xff\xfb" + b"\x00" * 100)  # fake MP3 bytes

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client(_fake_gemini_response(pcm)),
    ), patch("app.backends.tts.gemini.subprocess.run", side_effect=fake_run):
        backend = GeminiBackend(api_key="test-key")
        result = await backend.synthesize(
            "hello",
            voice="Kore",
            model="",
            output_path=out,
            format="mp3",
            style="",
        )

    assert any("ffmpeg" in " ".join(c) for c in ffmpeg_calls)
    assert any("libmp3lame" in c for call in ffmpeg_calls for c in call)
    assert result.format == "mp3"


@pytest.mark.asyncio
async def test_empty_candidates_raises(tmp_path: Path) -> None:
    out = tmp_path / "out.wav"

    with patch(
        "app.backends.tts.gemini.httpx.AsyncClient",
        return_value=_make_mock_client({"candidates": []}),
    ):
        backend = GeminiBackend(api_key="test-key")
        with pytest.raises(ValueError, match="No audio"):
            await backend.synthesize(
                "test", voice="", model="", output_path=out, format="wav", style=""
            )
```

- [ ] **Step 2: Run tests — expect ImportError**

```bash
uv run pytest tests/unit/test_backend_gemini.py -v
```

Expected: `ImportError: cannot import name 'GeminiBackend' from 'app.backends.tts.gemini'` (module doesn't exist yet).

---

### Task 1.2: Implement `GeminiBackend`

**Files:**
- Create: `app/backends/tts/gemini.py`

- [ ] **Step 1: Create implementation file**

`app/backends/tts/gemini.py`:

```python
"""Gemini 2.5 Flash TTS adapter — REST via httpx, PCM→WAV, ffmpeg for mp3/opus."""
from __future__ import annotations

import base64
import struct
import subprocess
import tempfile
from pathlib import Path

import httpx

from app.backends.tts.base import Format, TTSResult

DEFAULT_VOICE = "Charon"
DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a WAV container."""
    channels = 1
    bits_per_sample = 16
    data_size = len(pcm_bytes)
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,        # fmt chunk size
        1,         # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + pcm_bytes


class GeminiBackend:
    name = "gemini"
    default_voice = DEFAULT_VOICE
    normalizes_own_text = True  # capable model — handles acronyms and punctuation itself

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    async def synthesize(
        self,
        text: str,
        *,
        voice: str,
        model: str,
        output_path: Path,
        format: Format,
        style: str,
    ) -> TTSResult:
        _ = style  # Gemini TTS has no style/instruction parameter
        voice_id = voice or self.default_voice
        model_id = model or DEFAULT_MODEL

        url = f"{_GEMINI_API_BASE}/models/{model_id}:generateContent?key={self._api_key}"
        body = {
            "contents": [{"parts": [{"text": text}], "role": "user"}],
            "generationConfig": {
                "response_modalities": ["AUDIO"],
                "speech_config": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": voice_id}
                    }
                },
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=body)
        response.raise_for_status()

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("No audio in Gemini TTS response: missing candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("No audio in Gemini TTS response: missing parts")

        inline = parts[0].get("inlineData", {})
        audio_b64 = inline.get("data", "")
        raw_mime = inline.get("mimeType", "")

        if not audio_b64:
            raise ValueError("No audio in Gemini TTS response: empty data field")

        pcm_bytes = base64.b64decode(audio_b64)

        # Extract sample rate from MIME type (e.g. "audio/L16;rate=24000")
        sample_rate = 24000
        if "rate=" in raw_mime:
            try:
                sample_rate = int(raw_mime.split("rate=")[1].split(";")[0])
            except (ValueError, IndexError):
                pass

        duration_sec = len(pcm_bytes) / (sample_rate * 2)  # 16-bit = 2 bytes/sample, mono
        wav_bytes = _pcm_to_wav(pcm_bytes, sample_rate=sample_rate)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "wav":
            output_path.write_bytes(wav_bytes)
        else:
            with tempfile.TemporaryDirectory(prefix="gemini_tts_") as tmp:
                wav_path = Path(tmp) / "out.wav"
                wav_path.write_bytes(wav_bytes)
                codec = {"mp3": "libmp3lame", "opus": "libopus"}[format]
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-i", str(wav_path),
                        "-codec:a", codec,
                        str(output_path),
                    ],
                    check=True,
                )

        return TTSResult(
            audio_path=output_path,
            duration_sec=duration_sec,
            bytes=output_path.stat().st_size,
            voice=voice_id,
            backend="gemini",
            model=model_id,
            format=format,
        )
```

- [ ] **Step 2: Run tests — expect 3 passed**

```bash
uv run pytest tests/unit/test_backend_gemini.py -v
```

Expected:
```
test_synthesize_wav_output PASSED
test_mp3_output_converts_via_ffmpeg PASSED
test_empty_candidates_raises PASSED
3 passed
```

- [ ] **Step 3: Lint**

```bash
uv run ruff check app/backends/tts/gemini.py tests/unit/test_backend_gemini.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add app/backends/tts/gemini.py tests/unit/test_backend_gemini.py
git commit -m "feat(backends): Gemini 2.5 Flash TTS adapter"
```

---

## Phase 2 — Wire into factory + tool

### Task 2.1: Add Gemini voices to catalogue

**Files:**
- Modify: `app/backends/tts/voices.py`

- [ ] **Step 1: Add `GEMINI` list and update `for_backend()`**

In `app/backends/tts/voices.py`, add after the `OPENAI` list:

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

Replace `for_backend()`:

```python
def for_backend(backend: str) -> list[VoiceInfo]:
    return {
        "piper": PIPER,
        "gcloud": GCLOUD,
        "openai": OPENAI,
        "gemini": GEMINI,
    }.get(backend, [])
```

- [ ] **Step 2: Run smoke test**

```bash
uv run python -c "from app.backends.tts.voices import for_backend; print([v['id'] for v in for_backend('gemini')])"
```

Expected: `['Charon', 'Kore', 'Puck', 'Aoede', 'Fenrir', 'Leda', 'Orus', 'Zephyr']`

---

### Task 2.2: Add `gemini_api_key` to settings

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add field after `openai_api_key`**

In `app/config.py`, in the `Settings` class, add after the `openai_api_key` line:

```python
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
```

The block should look like:
```python
    groq_api_key: str = Field(default="", validation_alias="GROQ_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    google_application_credentials: str = Field(default="", validation_alias="GOOGLE_APPLICATION_CREDENTIALS")
```

- [ ] **Step 2: Verify settings still load**

```bash
uv run python -c "from app.config import get_settings; s = get_settings(); print('gemini_api_key OK:', repr(s.gemini_api_key))"
```

Expected: `gemini_api_key OK: ''`

---

### Task 2.3: Add `gemini` to the TTS backend factory

**Files:**
- Modify: `app/backends/__init__.py`

- [ ] **Step 1: Add import and factory branch**

In `app/backends/__init__.py`, add the import at the top with the other TTS imports:

```python
from app.backends.tts.gemini import GeminiBackend
```

In `get_tts_backend()`, add before the final `raise ValueError`:

```python
    if name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set; cannot use the gemini TTS backend")
        return GeminiBackend(api_key=settings.gemini_api_key)
```

The complete `get_tts_backend()` function should look like:

```python
def get_tts_backend(name: str, settings: Settings):
    if name == "piper":
        return PiperBackend(binary=settings.piper_binary, voice_dir=settings.piper_voice_dir)
    if name == "gcloud":
        if not settings.google_application_credentials:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS not set; cannot use the gcloud TTS backend"
            )
        return GCloudBackend()
    if name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not set; cannot use the openai TTS backend")
        return OpenAIBackend(api_key=settings.openai_api_key)
    if name == "gemini":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not set; cannot use the gemini TTS backend")
        return GeminiBackend(api_key=settings.gemini_api_key)
    raise ValueError(f"unknown TTS backend: {name!r}")
```

- [ ] **Step 2: Verify factory rejects unknown backend**

```bash
uv run python -c "
from app.config import Settings
from app.backends import get_tts_backend
s = Settings()
try:
    get_tts_backend('gemini', s)
except ValueError as e:
    print('OK:', e)
"
```

Expected: `OK: GEMINI_API_KEY not set; cannot use the gemini TTS backend`

---

### Task 2.4: Add `"gemini"` to `VALID_BACKENDS` in the tool

**Files:**
- Modify: `app/tools/generate_audio.py`

- [ ] **Step 1: Update the tuple**

In `app/tools/generate_audio.py`, change:

```python
VALID_BACKENDS = ("piper", "gcloud", "openai")
```

to:

```python
VALID_BACKENDS = ("piper", "gcloud", "openai", "gemini")
```

- [ ] **Step 2: Run all tests to confirm nothing is broken**

```bash
uv run pytest -v
```

Expected: all previously passing tests still pass + 3 new gemini unit tests = 70 passed.

- [ ] **Step 3: Lint**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit everything wired**

```bash
git add app/backends/tts/voices.py app/config.py app/backends/__init__.py app/tools/generate_audio.py
git commit -m "feat(backends): wire Gemini TTS backend into factory, config, and tool"
```

---

## Phase 3 — Infrastructure

### Task 3.1: Update `infra-poziomka` apps.yml

**Files:**
- Modify: `infra-poziomka/inventories/production/group_vars/poziomka/apps.yml` (in the `/Users/usterk/src/SukulaBloom/infra-poziomka` repo)

- [ ] **Step 1: Add `GEMINI_API_KEY` to audio-mcp env_vars**

In `inventories/production/group_vars/poziomka/apps.yml`, find the `audio-mcp:` section and add the env var:

```yaml
  audio-mcp:
    app_compose_template: audio-mcp/docker-compose.yml.j2
    app_env_vars:
      IMAGE_TAG: latest
      GROQ_API_KEY: "{{ vault_app_secrets['audio-mcp'].GROQ_API_KEY }}"
      OPENAI_API_KEY: "{{ vault_app_secrets['audio-mcp'].OPENAI_API_KEY }}"
      TS_AUTHKEY: "{{ vault_app_secrets['audio-mcp'].TS_AUTHKEY }}"
      GEMINI_API_KEY: "{{ vault_app_secrets['audio-mcp'].GEMINI_API_KEY }}"
```

- [ ] **Step 2: Verify vault already has `GEMINI_API_KEY`**

(The user has already added `GEMINI_API_KEY` to the vault during setup.)

```bash
cd /Users/usterk/src/SukulaBloom/infra-poziomka && \
  ANSIBLE_CONFIG=./ansible.cfg ansible-vault view \
  inventories/production/group_vars/poziomka/apps_vault.yml 2>/dev/null | \
  grep -A5 "audio-mcp:"
```

Expected: shows `GEMINI_API_KEY` key under `audio-mcp:`.

- [ ] **Step 3: Commit in infra-poziomka**

```bash
cd /Users/usterk/src/SukulaBloom/infra-poziomka
git add inventories/production/group_vars/poziomka/apps.yml
git commit -m "feat(audio-mcp): add GEMINI_API_KEY env var"
```

- [ ] **Step 4: Return to audio-mcp repo**

```bash
cd /Users/usterk/src/audio-mcp
```

---

## Phase 4 — Final verification

### Task 4.1: Full test suite + lint

**Files:** none

- [ ] **Step 1: Run complete test suite**

```bash
uv run pytest -v --tb=short
```

Expected: 70 passed (67 original + 3 gemini unit tests), 0 failed.

- [ ] **Step 2: Run ruff**

```bash
uv run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 3: Smoke test `list_voices` for gemini**

```bash
uv run python -c "
from app.backends.tts.voices import for_backend
voices = for_backend('gemini')
print(f'Gemini voices: {[v[\"id\"] for v in voices]}')
assert len(voices) == 8
print('OK')
"
```

Expected:
```
Gemini voices: ['Charon', 'Kore', 'Puck', 'Aoede', 'Fenrir', 'Leda', 'Orus', 'Zephyr']
OK
```
