"""`transcribe` MCP tool."""
from __future__ import annotations

import json
import tempfile
import time
import uuid as uuidlib
from pathlib import Path

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request

from app.backends import get_transcription_backend
from app.logging_setup import get_logger
from app.progress import ProgressReporter
from app.resolver import resolve_source
from app.storage.files import output_path
from app.tools._async_runner import run_with_soft_cap
from app.tools._eta import status_payload_with_queue

VALID_BACKENDS = ("groq", "local")
# Conservative initial estimate of audio length used to seed the queue
# before we have actually inspected the source. Once the resolver runs
# (and especially once the backend reports a real duration) the size_proxy
# and predicted_processing_sec are refined in jobs.db and the queue.
_SIZE_PROXY_FALLBACK_SEC = 600.0


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
        wait_max_sec: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Transcribe audio.

        The ``source`` may be a YouTube URL, an HTTP(S) URL to an audio file,
        an inline ``data:audio/...;base64,...`` payload (<= 10 MB), or a UUID
        returned by ``POST /upload``. Backends: ``groq`` (default, cloud)
        or ``local`` (faster-whisper, CPU). Returns a summary plus URLs for
        the JSON and TXT artefacts in the ``download`` field.

        ``wait_max_sec`` (default ``settings.default_wait_max_sec`` = 50)
        bounds how long the call may block. If the predicted total time
        exceeds the budget, the response returns immediately with status
        ``queued``/``running``, the job UUID, and ``check_after_sec`` —
        poll ``get_job(uuid)`` after that many seconds.
        """
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")

        state = _get_app_state()
        if state is None:
            raise RuntimeError("tool invoked outside of a configured app context")

        settings = getattr(state, "settings", None)
        jobs_db = getattr(state, "jobs_db", None)
        semaphores = getattr(state, "semaphores", None)
        job_queue = getattr(state, "job_queue", None)
        stats = getattr(state, "stats", None)
        background_tasks = getattr(state, "background_tasks", None)
        if (
            settings is None
            or jobs_db is None
            or semaphores is None
            or job_queue is None
            or stats is None
            or background_tasks is None
        ):
            raise RuntimeError("tool invoked outside of a configured app context")

        budget = wait_max_sec if wait_max_sec is not None else settings.default_wait_max_sec

        sem_backend = "faster_whisper" if backend == "local" else "groq"
        model_key = model or None

        # Seed prediction with a conservative audio length until the resolver
        # runs and we know the real value.
        initial_pred = stats.predict(
            kind="transcribe",
            backend=backend,
            model_key=model_key,
            size_proxy=_SIZE_PROXY_FALLBACK_SEC,
        )

        uuid = str(uuidlib.uuid4())
        await jobs_db.create_job(
            uuid=uuid,
            kind="transcribe",
            backend=backend,
            params={"source": source, "language": language, "model": model},
            predicted_processing_sec=initial_pred.seconds,
            model_key=model_key,
        )
        await job_queue.submit(
            uuid=uuid,
            sem_backend=sem_backend,
            predicted_proc_sec=initial_pred.seconds,
        )
        log = get_logger(__name__)
        log.info(
            "job_start",
            uuid=uuid,
            kind="transcribe",
            backend=backend,
            predicted_processing_sec=initial_pred.seconds,
        )

        reporter = ProgressReporter(ctx)

        async def _do_work() -> dict:
            try:
                await jobs_db.mark_started(uuid)
                await job_queue.start(uuid)
                start_mono = time.monotonic()
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

                            # YouTube transcript fast-path: duration available now.
                            if resolved.source_type == "youtube_transcript":
                                td = resolved.transcript_data or {}
                                early_audio_sec = float(td.get("duration") or 0.0)
                                if early_audio_sec > 0:
                                    refined = stats.predict(
                                        kind="transcribe",
                                        backend=backend,
                                        model_key=model_key,
                                        size_proxy=early_audio_sec,
                                    )
                                    await jobs_db.update_size_proxy(
                                        uuid,
                                        size_proxy=early_audio_sec,
                                        predicted_processing_sec=refined.seconds,
                                    )
                                    await job_queue.update_predicted(uuid, refined.seconds)

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
                            json_path.write_text(
                                json.dumps(transcription, ensure_ascii=False, indent=2)
                            )
                            txt_path.write_text(
                                _format_plain_text(transcription.get("segments", []) or [])
                                or transcription.get("text", "")
                            )
                    finally:
                        state.active_jobs -= 1
                processing_sec = time.monotonic() - start_mono

                audio_sec = float(transcription.get("duration", 0.0) or 0.0)
                if audio_sec > 0:
                    # Persist the actually-observed audio length and feed stats
                    # so subsequent calls predict more accurately.
                    await jobs_db.update_size_proxy(uuid, size_proxy=audio_sec)
                    stats.record(
                        kind="transcribe",
                        backend=backend,
                        model_key=model_key,
                        size_proxy=audio_sec,
                        processing_sec=processing_sec,
                    )

                await reporter.report(5, 5, "done")
                summary = _summary(transcription, backend)
                result_payload = {
                    "uuid": uuid,
                    "status": "done",
                    "was_async": False,
                    "summary": summary,
                    "duration_sec": audio_sec,
                    "language": transcription.get("language", ""),
                    "segments_count": len(transcription.get("segments", []) or []),
                    "download": {
                        "json": _download_url(settings, uuid, "json"),
                        "txt": _download_url(settings, uuid, "txt"),
                    },
                    "preview": (transcription.get("text") or "")[:500],
                    "processing_sec": processing_sec,
                    "predicted_processing_sec": initial_pred.seconds,
                    "size_proxy": audio_sec or None,
                    "model_key": model_key,
                }
                await jobs_db.mark_done(uuid, result=result_payload)
                log.info("job_done", uuid=uuid, processing_sec=processing_sec)
                return result_payload
            except Exception as exc:
                log.info("job_failed", uuid=uuid, error=str(exc))
                await jobs_db.mark_failed(uuid, error=str(exc))
                raise
            finally:
                await job_queue.complete(uuid)

        async def _async_payload() -> dict:
            row = await jobs_db.get_job(uuid)
            if row is None:
                return {
                    "uuid": uuid,
                    "status": "queued",
                    "was_async": True,
                    "message": "Job submitted; row not yet visible.",
                }
            payload = await status_payload_with_queue(
                job_row=row, queue=job_queue, base_url=settings.public_base_url
            )
            payload["was_async"] = True
            audio_min = (payload.get("size_proxy") or 0) / 60.0
            audio_blurb = f"{audio_min:.1f} min audio. " if audio_min > 0 else ""
            check_after = payload.get("check_after_sec") or 30
            payload["message"] = (
                f"{audio_blurb}Transcription should finish in "
                f"~{payload.get('eta_remaining_sec') or initial_pred.seconds:.0f}s. "
                f"Call get_job('{uuid}') after {check_after}s."
            )
            return payload

        # Decide effective wait: if predicted total clearly overshoots the
        # budget, return queued without burning the budget.
        snap = await job_queue.snapshot(uuid)
        predicted_wait = snap.predicted_wait_sec if snap is not None else 0.0
        predicted_total = predicted_wait + initial_pred.seconds
        effective_wait = budget if predicted_total <= budget else 0

        payload, _ = await run_with_soft_cap(
            coro=_do_work(),
            wait_max_sec=effective_wait,
            on_timeout=_async_payload,
            task_set=background_tasks,
        )
        return payload


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
