# audio-mcp — v1.0 Design

**Status:** proposed
**Date:** 2026-04-24
**Owner:** @usterk

## 1. Overview

`audio-mcp` is an MCP server providing two audio capabilities — transcription and text-to-speech —
deployed as a Docker container on the Aurora home-lab server, exposed only through the user's
Tailscale network. A single backend serves all clients (Claude Desktop, Claude Code, Gemini CLI,
a mobile agent, and Claude mobile), so API keys and model management live in one place.

Alongside the MCP endpoint, the service exposes a companion HTTP API for large file uploads and for
downloading generated transcriptions and audio files. MCP tool responses always include ready-made
download URLs; the HTTP API is a first-class surface, not a hidden implementation detail.

## 2. Goals

1. Single, remote MCP server usable by every supported client without private API keys on the client.
2. Transcription of YouTube URLs, remote HTTP audio file URLs, inline base64 payloads (≤10 MB),
   and previously uploaded files referenced by `upload_id`.
3. Text-to-speech with at least three backends (local free, cheap cloud, premium cloud) and
   per-language / per-voice text preprocessing (e.g., phonetic spelling of acronyms for Polish TTS,
   removal of URLs and long hashes).
4. No visible request timeouts for long-running jobs: transcription of a 60-minute audio file on CPU
   must not require special client configuration beyond raising the MCP client's per-server timeout.
5. Deploy via existing `infra-poziomka` Ansible role + GitHub Actions (build → push GHCR → SSH deploy)
   using the same pattern as FlowOS.
6. Test coverage ≥ 80 % enforced in CI.

## 3. Non-goals (v1.0)

- Public internet exposure. Access is tailnet-only; no login, tokens, or multi-tenant auth.
- Speaker diarization. whisperx/PyAnnote on CPU is prohibitively slow; revisit when GPU is available.
- Spotify podcast audio. DRM and ToS rule it out; v1.1 may add a `resolve_podcast(title)` helper that
  searches YouTube for candidates (read-only, no audio fetch from Spotify).
- LLM-based text normalization. Rule-based normalization is sufficient for v1.0.
- Additional TTS model families beyond `piper`, Google Cloud TTS Standard, and OpenAI
  `gpt-4o-mini-tts`. Gemini TTS, Google Neural2/Studio, and `tts-1-hd` are candidates for v1.1.
- Async-task (submit / poll) tool pattern. Kept as an escape hatch if long-lived sessions prove
  unstable in practice; MVP uses synchronous tools with progress notifications and a job recovery
  tool.

## 4. Users and clients

All clients connect over Tailscale to the `audio-mcp` MagicDNS hostname:

| Client | Transport | Notes |
|---|---|---|
| Claude Desktop | MCP streamable HTTP | Config entry in `claude_desktop_config.json`. |
| Claude Code | MCP streamable HTTP | Config entry in `~/.claude/.mcp.json`; may need `MCP_TIMEOUT` bumped. |
| Gemini CLI | MCP streamable HTTP | Client-side docs vary; `usage_guide()` tool and `instructions` field compensate for weaker resource support. |
| Mobile agent | MCP streamable HTTP | Implementation-dependent; same URL. |
| Claude mobile | MCP streamable HTTP | Same URL. |

Tailscale provides network-level authentication. The service trusts every request reaching it.

## 5. High-level architecture

```
┌─────────────── Aurora (Ubuntu, Docker, /opt/apps/audio-mcp) ────────────────┐
│                                                                              │
│  ┌─────── ts-audio-mcp (tailscale/tailscale) ─────────┐                      │
│  │  hostname: audio-mcp                                │                      │
│  │  Tailscale Serve: :443 (HTTPS) → :8000 (app)       │                      │
│  └────────────────────────────────────────────────────┘                      │
│                       ▲                                                      │
│                       │ network_mode: service:ts-audio-mcp                   │
│                       ▼                                                      │
│  ┌─────── audio-mcp (app container, :8000) ──────────┐                       │
│  │  Python 3.12 · uvicorn · FastAPI + FastMCP        │                       │
│  │                                                    │                       │
│  │  HTTP:   POST /upload                              │                       │
│  │          GET  /uploads/{upload_id}                 │                       │
│  │          GET  /jobs/{uuid}                         │                       │
│  │          GET  /jobs/{uuid}/transcription.json|txt  │                       │
│  │          GET  /jobs/{uuid}/audio.mp3|wav|opus      │                       │
│  │          GET  /health   GET /  (landing page)      │                       │
│  │                                                    │                       │
│  │  MCP:    POST /mcp (streamable HTTP)               │                       │
│  │                                                    │                       │
│  │  Modules: tools/ backends/ preprocessing/ storage/ │                       │
│  │                                                    │                       │
│  │  Volumes: /app/data/{uploads,outputs,jobs.db}      │                       │
│  │  Secrets (env): GROQ_API_KEY, OPENAI_API_KEY       │                       │
│  │           (file): /secrets/gcp.json                │                       │
│  └────────────────────────────────────────────────────┘                      │
└──────────────────────────────────────────────────────────────────────────────┘

Clients (all on the tailnet)
  Claude Desktop / Claude Code / Gemini CLI / Mobile agent / Claude mobile
      │
      ▼
  https://audio-mcp.<tailnet>.ts.net/mcp      (MCP streamable HTTP)
  https://audio-mcp.<tailnet>.ts.net/upload   (multipart POST)
  https://audio-mcp.<tailnet>.ts.net/jobs/... (downloads)
```

A single uvicorn worker hosts both the FastAPI app and the FastMCP ASGI sub-app mounted at `/mcp`.
One worker is intentional: shared in-process state (semaphores, SQLite job store) is simpler to
reason about and five concurrent clients fit comfortably within asyncio.

## 6. MCP tools

### 6.1 `transcribe`

```python
transcribe(
    source: str,                 # YouTube URL | HTTP(S) URL | "data:audio/...;base64,..." | upload_id (UUID)
    backend: str = "groq",       # "groq" | "local"
    language: str = "",          # ISO-639-1, "" = auto
    model: str = "",             # override backend default
) -> {
    "uuid": str,
    "summary": str,              # e.g., "12.3 min, lang=pl, 87 segments, backend=groq"
    "duration_sec": float,
    "language": str,
    "segments_count": int,
    "download": {
        "json": "https://audio-mcp.<tailnet>.ts.net/jobs/{uuid}/transcription.json",
        "txt":  "https://audio-mcp.<tailnet>.ts.net/jobs/{uuid}/transcription.txt",
    },
    "preview": str,              # first ~500 chars of text for in-conversation display
}
```

Backend defaults:
- `groq` → `whisper-large-v3-turbo`
- `local` (faster-whisper, CTranslate2, CPU) → `small` (good Polish, practical speed on CPU;
  users can override to `tiny` / `base` / `medium` / `large-v3`).

Source type is auto-detected:
- `data:audio/...;base64,...` → inline payload (hard cap 10 MB; above that, return an error with a
  pointer to `POST /upload` and `usage_guide()`).
- Valid UUIDv4 string that exists in `/data/uploads/` → previously uploaded file.
- URL matching YouTube patterns → YouTube branch (transcript API fast path; if `backend == "local"`,
  force audio download).
- Other HTTP(S) URL → fetch audio via `yt-dlp` or direct HTTP; accept common audio/video containers.

### 6.2 `generate_audio`

```python
generate_audio(
    text: str,
    backend: str = "piper",      # "piper" | "gcloud" | "openai"
    voice: str = "",             # per-backend default (piper → gosia-medium, gcloud → pl-PL-Standard-A)
    model: str = "",             # for "openai": "gpt-4o-mini-tts" (default)
    language: str = "pl",        # drives preprocessing dictionary
    normalize: str = "basic",    # "basic" | "none"  (v1.0; "llm" reserved for v1.1)
    style: str = "",             # openai gpt-4o-mini-tts only: free-form style instruction
    format: str = "mp3",         # "mp3" | "wav" | "opus"
) -> {
    "uuid": str,
    "duration_sec": float,
    "bytes": int,
    "voice": str,
    "backend": str,
    "download": {
        "audio": "https://audio-mcp.<tailnet>.ts.net/jobs/{uuid}/audio.mp3",
    },
    "normalized_text": str,      # text actually sent to the TTS backend (for debugging)
}
```

### 6.3 Helper tools

- `list_voices(backend: str) -> list[{id, name, language, gender, tags}]` — static registry per
  backend, loaded at startup.
- `list_recent_jobs(limit: int = 10) -> list[{uuid, kind, backend, status, created_at, download}]` —
  safety net when a long job's session dropped.
- `usage_guide() -> str` — returns the full agent-facing markdown guide (same content as the
  `audio-mcp://docs/usage` resource).

### 6.4 MCP resources

- `audio-mcp://docs/usage` — rendered from `docs/usage.md` at startup, single source of truth with
  workflow examples, upload instructions, backend selection tips. Clients that support resources
  (Claude Desktop, Claude Code) can list and read it; others fall back to `usage_guide()`.

### 6.5 MCP server instructions

Set on the FastMCP server at construction time. Example:

> *"This server offers two tools: `transcribe` (YouTube, audio URL, base64, or upload_id) and
> `generate_audio` (Polish-aware TTS). For files >10 MB, first POST them to `/upload` and pass the
> returned `upload_id` as `source`. Results are downloadable via URLs returned in the `download`
> field of each tool response. For a full workflow, call `usage_guide()` or read the
> `audio-mcp://docs/usage` resource."*

## 7. HTTP API

| Method | Path | Purpose | Response |
|---|---|---|---|
| `POST` | `/upload` | `multipart/form-data` with `file` field | `{upload_id, size_bytes, content_type, expires_at}` |
| `GET`  | `/uploads/{upload_id}` | Existence / metadata probe | `{upload_id, size_bytes, content_type, created_at, expires_at}` or 404 |
| `GET`  | `/jobs/{uuid}` | Job metadata | `{uuid, kind, status, backend, created_at, download}` |
| `GET`  | `/jobs/{uuid}/transcription.json` | Full JSON transcript | JSON file |
| `GET`  | `/jobs/{uuid}/transcription.txt` | Formatted plain text | `text/plain; charset=utf-8` |
| `GET`  | `/jobs/{uuid}/audio.{mp3,wav,opus}` | Generated TTS audio | `audio/mpeg` etc. |
| `GET`  | `/health` | Liveness + quick diagnostics | `{status, version, uptime_sec, active_jobs, backends_loaded}` |
| `GET`  | `/`     | Minimal HTML landing page | Human-readable info + MCP URL |

Upload size limit: 500 MB (configurable via env). Upload TTL: 24 h (cron-style cleanup in-process).

## 8. Storage and data model

```
/opt/apps/audio-mcp/data/     # volume-mounted at /app/data
├── uploads/<upload_id>.<ext>   # raw uploads, TTL 24h
├── outputs/<uuid>.json         # transcription JSON
├── outputs/<uuid>.txt          # transcription plain text
├── outputs/<uuid>.mp3          # generated audio (or .wav/.opus)
└── jobs.db                     # SQLite
```

SQLite schema (`jobs.db`, via `aiosqlite`):

```sql
CREATE TABLE jobs (
    uuid        TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,      -- 'transcribe' | 'generate_audio'
    backend     TEXT NOT NULL,
    status      TEXT NOT NULL,      -- 'running' | 'done' | 'failed'
    params_json TEXT NOT NULL,
    result_json TEXT,               -- populated when done
    error       TEXT,
    created_at  INTEGER NOT NULL,
    finished_at INTEGER
);
CREATE INDEX jobs_created_at ON jobs (created_at DESC);

CREATE TABLE uploads (
    upload_id    TEXT PRIMARY KEY,
    size_bytes   INTEGER NOT NULL,
    content_type TEXT,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL
);
```

Jobs are written at start (`status='running'`) and updated on completion. This is what powers
`list_recent_jobs` and the `/jobs/{uuid}` metadata endpoint.

## 9. Backends

### 9.1 Transcription

| Backend | Engine | Default model | Requires | Notes |
|---|---|---|---|---|
| `groq` | Groq Whisper API | `whisper-large-v3-turbo` | `GROQ_API_KEY` | Fast cloud, default. |
| `local` | `faster-whisper` (CTranslate2) | `small` | — | Runs on CPU, ~2–4× faster than whisper.cpp at equal quality. |

YouTube fast path: when `backend == "groq"` and the video has transcripts, use
`youtube-transcript-api` to skip audio download entirely. If transcripts are unavailable for a
given video (common for recently uploaded or non-English videos), fall back to downloading the
audio via `yt-dlp` and running it through Groq Whisper. For `backend == "local"`, always download
audio and run it through faster-whisper.

Audio retrieval: `yt-dlp` for YouTube and arbitrary HTTP URLs, falling back to plain HTTP download
for direct audio files. `ffmpeg` normalizes to 16 kHz mono WAV for whisper backends.

### 9.2 TTS

| Backend | Engine | Default voice | Requires | Notes |
|---|---|---|---|---|
| `piper` | piper-tts (native binary) | `gosia-medium` (PL) | — | Runs on CPU inside the container. Default. |
| `gcloud` | Google Cloud Text-to-Speech Standard | `pl-PL-Standard-A` | `GOOGLE_APPLICATION_CREDENTIALS` pointing to `/secrets/gcp.json` | Cheapest cloud option. |
| `openai` | OpenAI `gpt-4o-mini-tts` | `nova` | `OPENAI_API_KEY` | Supports `style` parameter (e.g., "say calmly, slowly"). |

The `piper` binary and the `gosia-medium` voice files are baked into the Docker image at build time
via `scripts/download_piper_voice.sh`, so the container is self-contained.

## 10. Text preprocessing

Applied before sending text to a TTS backend, controlled by `normalize` parameter.

`normalize="basic"` (default):
1. Strip Markdown syntax (headers, emphasis, code fences) — pass through text only.
2. Replace HTTP/HTTPS URLs with an empty string (or a short placeholder like "link"; configurable
   per-language).
3. Replace long hex/base64 strings (e.g., SHA hashes, ≥32 alphanumeric chars) with empty string.
4. For `language="pl"`: look up an acronym dictionary (~50 entries, e.g., `FBI` → `ef bi aj`,
   `API` → `a-pi-aj`, `USA` → `u-es-ej`, `NATO` → `nato`, `ONZ` → `o-en-zet`). Case-sensitive;
   matches standalone tokens only.
5. Normalize whitespace.

`normalize="none"` bypasses the pipeline.

Per-backend override: the registry can mark a backend as "self-normalizing". `openai` defaults to
`none` because `gpt-4o-mini-tts` handles acronyms and punctuation well on its own; users can still
force `basic` via the parameter. `piper` and `gcloud` default to `basic`.

The preprocessing dictionary lives in `app/preprocessing/dictionary/pl.json` and is loaded at
startup; it is easy to extend without code changes.

## 11. Timeout mitigation

MCP clients impose per-tool timeouts; long local transcription on CPU (up to ~15 min for 60 min
audio) would otherwise trip them. Mitigations, in order of importance:

1. **Streamable HTTP transport** (MCP spec 2025-03-26): long-lived SSE-style connections with
   interleaved JSON chunks keep the session active as long as the server sends events.
2. **Progress notifications** every 2–5 s during any long-running tool, emitted via
   `ctx.report_progress(step, total, message)`. Each notification is a visible event to the
   transport layer, preventing idle timeouts.
3. **Heartbeat**: if the active backend does not report progress for >15 s, a background task
   emits an empty progress tick so the connection stays busy.
4. **Client-side timeout bump**: per-client docs in the README (e.g., `"timeout": 900000` in
   `~/.claude/.mcp.json` → 15 min).
5. **Job recovery tool** `list_recent_jobs`: jobs are always persisted to SQLite at start and
   finalized on completion. If a session dies mid-call, the client can recover the result on
   reconnect. This is a small amount of state, not a full async task API — no second
   `get_status(task_id)` call required in the happy path.

If real-world usage later shows connections dropping despite (1)–(4), the escape hatch is to add a
dedicated `submit_transcribe` + `get_result` pair (pattern already sketched in the job store). That
is deferred, not built.

## 12. Concurrency model

Single-worker uvicorn with asyncio. Two layers of semaphores:

- Global: `asyncio.Semaphore(5)` on every tool call. Five concurrent clients is the declared target.
- Per-CPU-backend: `asyncio.Semaphore(2)` on `faster-whisper` and `piper` to bound CPU pressure.
  Cloud backends (`groq`, `gcloud`, `openai`) are I/O-bound and only use the global semaphore.

CPU-bound work runs inside `asyncio.to_thread(...)` to avoid blocking the event loop. For `piper`
and `faster-whisper`, this wraps a synchronous call site; for `groq`/`openai`/`gcloud`, the
respective SDKs are used in their native async mode or wrapped identically.

## 13. Agent documentation strategy (five layers)

To help every client understand the server's full surface (not just the MCP tools but also
`/upload` and `/jobs/...`), the same information is exposed in five places:

1. **Server `instructions`** — set on FastMCP construction; clients receive it on `initialize`.
2. **Tool docstrings** — serialized into `tools/list`; cover `source` formats, timeout notes,
   behavior of `download` fields.
3. **`usage_guide()` tool** — returns the full Markdown guide, for clients with weak resource
   support (e.g., Gemini CLI).
4. **`audio-mcp://docs/usage` resource** — same content, for clients that support resources.
5. **Contextual hints in tool responses** — every `transcribe` and `generate_audio` reply includes
   a `download.*` field with concrete URLs; errors for oversize base64 payloads include an actionable
   pointer to `POST /upload` and `usage_guide()`.

`usage_guide()` and the resource share a single source: `docs/usage.md` bundled in the image.

## 14. Deployment

### 14.1 Dockerfile

Multi-stage, slim runtime: Python 3.12 slim + `ffmpeg` + `curl` + `piper` binary + bundled voice.

### 14.2 infra-poziomka integration

Follow the same app pattern already used for FlowOS:

- `roles/app/templates/audio-mcp/docker-compose.yml.j2` — Tailscale sidecar with hostname
  `audio-mcp`, plus the app container sharing the sidecar's network namespace (`network_mode:
  service:ts-audio-mcp`). Volume mounts: `data/` for uploads/outputs/jobs.db, `ts-config/serve.json`
  for the Serve config, `gcp-credentials.json` for the Google TTS service account.
- `roles/app/templates/audio-mcp/serve.json.j2` — Tailscale Serve TLS on :443 proxying to
  `http://127.0.0.1:8000`.
- `inventories/production/group_vars/poziomka/apps.yml` — new `audio-mcp` entry referencing the
  templates, with `IMAGE_TAG` and non-secret env vars.
- `inventories/production/group_vars/poziomka/apps_vault.yml` — secrets: `TS_AUTHKEY`,
  `GROQ_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_TTS_SERVICE_ACCOUNT_JSON` (full JSON body). The Ansible
  role writes the last one to `/opt/apps/audio-mcp/gcp-credentials.json` before container start;
  the Docker Compose file then bind-mounts it read-only into the app container at
  `/secrets/gcp.json`, and `GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json` is set via
  `environment:` so the Google SDK picks it up automatically.

Deploy (manual): `ansible-playbook playbooks/deploy-app.yml -e "target_app=audio-mcp"`.

### 14.3 CI/CD — GitHub Actions

Two workflows, mirroring FlowOS.

**`.github/workflows/test.yml`** — triggered on push to `main` and every PR:
- Installs `ffmpeg` and `piper` binary.
- Pre-downloads piper `gosia-medium` voice and faster-whisper `tiny` model (cached across runs).
- Runs `pytest` with `--cov=app --cov-fail-under=80`.
- Uploads test results and coverage artifacts.
- Posts a sticky PR summary comment.

**`.github/workflows/deploy.yml`** — triggered by successful `Tests` workflow run on `main` or by
manual dispatch:
- Builds the Docker image and pushes to `ghcr.io/usterk/audio-mcp:v<version>` + `:latest` using
  `scripts/version.py` (version derived from `pyproject.toml`).
- Connects to Tailscale via the `tailscale/github-action@v4` GH Action (OAuth client
  stored in repo secrets `TS_OAUTH_CLIENT_ID` / `TS_OAUTH_SECRET`).
- SSHes into `usterk@aurora`, pulls the new image, updates `IMAGE_TAG` in `.env`, runs
  `docker compose up -d --remove-orphans --force-recreate`, waits, calls `/health` for a health
  check, then `docker image prune -f`.

## 15. Testing strategy

Target: ≥ 80 % coverage, enforced via `--cov-fail-under=80`.

- **Unit tests** (`tests/unit/`): pure-Python modules in isolation.
  - Source resolver (YouTube URL parsing, data URI parsing, base64 decoding, upload_id lookup).
  - Preprocessing rules (URL/hash stripping, acronym dictionary, idempotence).
  - Cloud backends via HTTP mocks (`respx` / `pytest-httpx`): `groq`, `gcloud`, `openai`.
  - SQLite jobs DB — CRUD, lifecycle transitions, idempotence on restart.
  - Semaphores and concurrency helpers (async stubs).
  - File storage helpers (path sanitization, TTL cleanup).

- **Integration tests** (`tests/integration/`): FastAPI TestClient + real local backends.
  - `POST /upload` then `transcribe(source=upload_id)` happy path using a 5-second fixture.
  - `generate_audio(backend="piper", text="...")` end-to-end, verifying output file metadata.
  - `faster-whisper tiny` transcription on a short fixture — quick but meaningful.
  - Cloud backends remain mocked to keep CI offline and free.

- **MCP smoke tests** (`tests/mcp/`): in-process MCP client (Python `mcp.client`) speaks to the
  server via the streamable HTTP endpoint.
  - Verifies `initialize` returns the expected `instructions`.
  - Lists and calls `usage_guide`, `list_voices`, `list_recent_jobs`.
  - Calls `generate_audio(backend="piper")` end to end, then `GET /jobs/{uuid}/audio.mp3`.

Fixtures: a ~5-second polyglot speech clip (`tests/fixtures/short_pl.wav`, `short_en.wav`) checked
in to keep tests deterministic.

## 16. Observability

- **Structured JSON logs to stdout** — one line per event. Shared fields: `ts`, `level`, `event`,
  `uuid`, `tool`, `backend`, `duration_ms`, `error`. Docker captures them for local inspection.
- **`/health`** returns `{status, version, uptime_sec, active_jobs, backends_loaded}`.
- **`/metrics`** (optional Prometheus text format, gated by env flag): `audio_mcp_jobs_total`,
  `audio_mcp_job_duration_seconds`, `audio_mcp_semaphore_in_use`. Disabled by default; can be turned
  on without code changes if a metrics stack appears on Aurora.
- **Upload cleanup** runs in-process via `apscheduler` (tick every 60 min) and logs the number of
  removed files.

## 17. Security

- **Transport**: Tailscale-only. TLS is terminated by the Tailscale Serve sidecar; no self-managed
  cert or ACME flow.
- **Auth**: none beyond tailnet membership. Adding a static bearer token later is a trivial
  addition (single FastAPI dependency + env var) if a guest is ever invited to the tailnet.
- **Secrets**: managed entirely by Ansible Vault; never baked into Docker images.
- **Uploads**: server-assigned UUID filenames, content-type sniffing with `python-magic`, size cap,
  24 h TTL. Large uploads streamed directly to disk (no in-memory buffering).
- **Rate limits**: not in v1.0. If it becomes relevant, a small FastAPI middleware (e.g.,
  `slowapi`) can be added later.

## 18. MVP acceptance checklist

- [ ] FastAPI + FastMCP monolith, streamable HTTP at `/mcp`.
- [ ] Tools: `transcribe`, `generate_audio`, `list_voices`, `list_recent_jobs`, `usage_guide`.
- [ ] Resource: `audio-mcp://docs/usage`.
- [ ] HTTP: `/upload`, `/uploads/{id}`, `/jobs/{uuid}`, `/jobs/{uuid}/transcription.{json,txt}`,
      `/jobs/{uuid}/audio.{mp3,wav,opus}`, `/health`, `/` landing.
- [ ] Transcription backends: `groq` (default) and `faster-whisper` (CPU, default model `small`).
- [ ] TTS backends: `piper` (default, `gosia-medium`), `gcloud` Standard, `openai gpt-4o-mini-tts`.
- [ ] Preprocessing: rules + PL acronym dictionary, per-backend default, `normalize` parameter.
- [ ] Concurrency: global `Semaphore(5)` + per-CPU-backend semaphores.
- [ ] Timeout mitigation: progress notifications + heartbeat + `list_recent_jobs` recovery.
- [ ] Five-layer agent documentation.
- [ ] SQLite jobs store, upload cleanup, output file layout.
- [ ] Dockerfile baking piper + gosia voice; image builds < 1 GB.
- [ ] Ansible template + `apps.yml` / `apps_vault.yml` entries in `infra-poziomka`.
- [ ] `test.yml` with `--cov-fail-under=80` gate.
- [ ] `deploy.yml` mirroring FlowOS (Tailscale OAuth + SSH deploy).
- [ ] README with per-client connection snippets.

## 19. Out of scope / future work

- Speaker diarization (`local-diarize` backend) once GPU is available.
- LLM-based text normalization (`normalize="llm"`).
- Additional TTS model families: Gemini TTS (2.5 Flash), Google Neural2/Studio, OpenAI `tts-1-hd`.
- `resolve_podcast(title)` helper (Spotify title → YouTube candidates).
- `submit_transcribe` / `get_result` explicit async pattern for extreme-length jobs.
- Per-user auth (Tailscale identity via `tailscale whois`).
- Prometheus + Grafana integration once a monitoring stack is deployed on Aurora.
- Companion local `say-mcp` server (stdio, macOS-only) reusing the same preprocessing package — if
  `say` quality ever becomes compelling for specific use cases.
