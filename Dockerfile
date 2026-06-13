# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

FROM python:3.12-slim AS runtime
# App version baked at build time by the Aurora runner; read at runtime (version.py).
ARG APP_VERSION=0.0.0-dev
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    AUDIO_MCP_DATA_DIR=/app/data \
    AUDIO_MCP_PIPER_VOICE_DIR=/app/models/piper \
    APP_VERSION=${APP_VERSION}
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl ca-certificates unzip && rm -rf /var/lib/apt/lists/*

# Deno — JavaScript runtime used by yt-dlp for newer YouTube extraction paths.
ARG DENO_VERSION=v2.1.4
RUN curl -fsSL "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
    -o /tmp/deno.zip \
    && unzip /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && chmod +x /usr/local/bin/deno

# Piper binary
ARG PIPER_VERSION=2023.11.14-2
RUN curl -fsSL "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz" \
    | tar -xz -C /opt \
    && ln -s /opt/piper/piper /usr/local/bin/piper

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app/
COPY docs/ ./docs/
COPY scripts/ ./scripts/
COPY pyproject.toml ./
RUN bash scripts/download_piper_voice.sh gosia-medium

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s \
    CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
