"""`transcribe` MCP tool."""
from __future__ import annotations

import json
import tempfile
import uuid as uuidlib
from pathlib import Path

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request

from app.backends import get_transcription_backend
from app.logging_setup import get_logger
from app.progress import ProgressReporter
from app.resolver import resolve_source
from app.storage.files import output_path

VALID_BACKENDS = ("groq", "local")


def _download_url(settings, uuid: str, ext: str) -> str:
    base = settings.public_base_url.rstrip("/")
    return f"{base}/jobs/{uuid}/{'transcription' if ext in ('json', 'txt') else 'audio'}.{ext}"


def _get_app_state():
    """Retrieve the FastAPI app state from the current HTTP request."""
    try:
        request = get_http_request()
        return request.app.state
    except RuntimeError:
        return None


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def transcribe(
        source: str,
        backend: str = "groq",
        language: str = "",
        model: str = "",
        ctx: Context | None = None,
    ) -> dict:
        """Transcribe audio.

        The `source` may be a YouTube URL, an HTTP(S) URL to an audio file,
        an inline ``data:audio/...;base64,...`` payload (<= 10 MB), or a UUID
        returned by ``POST /upload``. Backends: ``groq`` (default, cloud)
        or ``local`` (faster-whisper, CPU). Returns a summary plus URLs for
        the JSON and TXT artefacts in the ``download`` field.
        """
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")

        state = _get_app_state()
        if state is None:
            raise RuntimeError("tool invoked outside of a configured app context")

        settings = getattr(state, "settings", None)
        jobs_db = getattr(state, "jobs_db", None)
        semaphores = getattr(state, "semaphores", None)
        if settings is None or jobs_db is None or semaphores is None:
            raise RuntimeError("tool invoked outside of a configured app context")

        reporter = ProgressReporter(ctx)
        uuid = str(uuidlib.uuid4())
        await jobs_db.create_job(
            uuid=uuid,
            kind="transcribe",
            backend=backend,
            params={"source": source, "language": language, "model": model},
        )
        get_logger(__name__).info("job_start", uuid=uuid, kind="transcribe", backend=backend)
        sem_backend = "faster_whisper" if backend == "local" else "groq"

        try:
            async with semaphores.slot(sem_backend):
                state.active_jobs += 1
                try:
                    await reporter.report(1, 5, "resolving source")
                    with tempfile.TemporaryDirectory(prefix="audio_mcp_") as tmp:
                        resolved = await resolve_source(
                            source,
                            settings=settings,
                            work_dir=Path(tmp),
                            prefer_audio=(backend == "local"),
                            languages=[language] if language else None,
                        )

                        await reporter.report(2, 5, "transcribing audio")

                        if resolved.source_type == "youtube_transcript":
                            transcription = resolved.transcript_data
                            transcription.setdefault("backend", "youtube_transcript")
                            transcription.setdefault("model", "")
                        else:
                            async with reporter.heartbeat(total=5, message="transcribing"):
                                tbackend = get_transcription_backend(backend, settings)
                                result = await tbackend.transcribe(
                                    resolved.audio_path,
                                    language=language or None,
                                    model=model or None,
                                )
                            transcription = {
                                "segments": result.segments,
                                "text": result.text,
                                "duration": result.duration,
                                "language": result.language,
                                "backend": result.backend,
                                "model": result.model,
                            }

                        await reporter.report(3, 5, "writing artefacts")
                        json_path = output_path(settings.data_dir, uuid, "transcription", "json")
                        txt_path = output_path(settings.data_dir, uuid, "transcription", "txt")
                        json_path.parent.mkdir(parents=True, exist_ok=True)
                        json_path.write_text(json.dumps(transcription, ensure_ascii=False, indent=2))
                        txt_path.write_text(
                            _format_plain_text(transcription.get("segments", []) or [])
                            or transcription.get("text", "")
                        )

                finally:
                    state.active_jobs -= 1

            await reporter.report(5, 5, "done")
            summary = _summary(transcription, backend)
            result_payload = {
                "uuid": uuid,
                "summary": summary,
                "duration_sec": float(transcription.get("duration", 0.0) or 0.0),
                "language": transcription.get("language", ""),
                "segments_count": len(transcription.get("segments", []) or []),
                "download": {
                    "json": _download_url(settings, uuid, "json"),
                    "txt": _download_url(settings, uuid, "txt"),
                },
                "preview": (transcription.get("text") or "")[:500],
            }
            await jobs_db.mark_done(uuid, result=result_payload)
            get_logger(__name__).info("job_done", uuid=uuid)
            return result_payload
        except Exception as exc:
            get_logger(__name__).info("job_failed", uuid=uuid, error=str(exc))
            await jobs_db.mark_failed(uuid, error=str(exc))
            raise


def _format_plain_text(segments: list[dict]) -> str:
    lines: list[str] = []
    prev_end: float | None = None
    for s in segments:
        if prev_end is not None and (s.get("start", 0) - prev_end) > 2:
            lines.append("")
        lines.append(s.get("text", "").strip())
        prev_end = s.get("end")
    return "\n".join(lines)


def _summary(transcription: dict, backend: str) -> str:
    parts: list[str] = []
    dur = float(transcription.get("duration", 0.0) or 0.0)
    if dur:
        parts.append(f"{dur / 60:.1f} min")
    if transcription.get("language"):
        parts.append(f"lang={transcription['language']}")
    parts.append(f"{len(transcription.get('segments', []) or [])} segments")
    parts.append(f"backend={transcription.get('backend') or backend}")
    return ", ".join(parts)
