"""`generate_audio` MCP tool."""
from __future__ import annotations

import uuid as uuidlib

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request

from app.backends import get_tts_backend
from app.preprocessing import normalize_text
from app.progress import ProgressReporter
from app.storage.files import output_path

VALID_BACKENDS = ("piper", "gcloud", "openai")
VALID_FORMATS = ("mp3", "wav", "opus")
VALID_NORMALIZE = ("basic", "none")


def _download_url(settings, uuid: str, ext: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/jobs/{uuid}/audio.{ext}"


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def generate_audio(
        text: str,
        backend: str = "piper",
        voice: str = "",
        model: str = "",
        language: str = "pl",
        normalize: str = "basic",
        style: str = "",
        format: str = "mp3",
        ctx: Context | None = None,
    ) -> dict:
        """Generate an audio file from text.

        Backends: ``piper`` (default, local CPU, free), ``gcloud``
        (Google Cloud TTS Standard), ``openai`` (gpt-4o-mini-tts, supports
        a ``style`` instruction). Text preprocessing (``normalize='basic'``)
        replaces URLs, long hashes and Polish acronyms with phonetic
        spellings before sending to the backend. Use ``normalize='none'``
        to bypass preprocessing entirely.
        """
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")
        if format not in VALID_FORMATS:
            raise ValueError(f"format must be one of {VALID_FORMATS}")
        if normalize not in VALID_NORMALIZE:
            raise ValueError(f"normalize must be one of {VALID_NORMALIZE}")

        request = get_http_request()
        app = request.app
        settings = app.state.settings
        jobs_db = app.state.jobs_db
        semaphores = app.state.semaphores

        reporter = ProgressReporter(ctx)
        uuid = str(uuidlib.uuid4())
        await jobs_db.create_job(
            uuid=uuid,
            kind="generate_audio",
            backend=backend,
            params={
                "text_length": len(text),
                "voice": voice,
                "model": model,
                "language": language,
                "normalize": normalize,
                "format": format,
            },
        )

        tts = get_tts_backend(backend, settings)
        effective_mode = normalize
        if tts.normalizes_own_text and normalize == "basic":
            effective_mode = "none"
        normalized = normalize_text(text, language=language, mode=effective_mode)

        try:
            async with semaphores.slot(backend):
                app.state.active_jobs += 1
                try:
                    await reporter.report(1, 3, "synthesising audio")
                    out_path = output_path(settings.data_dir, uuid, "audio", format)
                    async with reporter.heartbeat(total=3, message="synthesising"):
                        result = await tts.synthesize(
                            normalized,
                            voice=voice or tts.default_voice,
                            model=model,
                            output_path=out_path,
                            format=format,
                            style=style,
                        )
                    await reporter.report(2, 3, "writing artefact")
                finally:
                    app.state.active_jobs -= 1

            response = {
                "uuid": uuid,
                "duration_sec": result.duration_sec,
                "bytes": result.bytes,
                "voice": result.voice,
                "backend": result.backend,
                "model": result.model,
                "format": result.format,
                "download": {"audio": _download_url(settings, uuid, format)},
                "normalized_text": normalized,
            }
            await jobs_db.mark_done(uuid, result=response)
            await reporter.report(3, 3, "done")
            return response
        except Exception as exc:
            await jobs_db.mark_failed(uuid, error=str(exc))
            raise
