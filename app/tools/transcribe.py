"""`transcribe` MCP tool."""
from __future__ import annotations

import json
import tempfile
import time
import uuid as uuidlib
from pathlib import Path
from typing import Literal

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request
from groq import APIError, APIStatusError
from mcp.types import ToolAnnotations

from app.audio.compress import compress_for_groq
from app.backends import get_transcription_backend
from app.logging_setup import get_logger
from app.progress import ProgressReporter
from app.resolver import resolve_source
from app.storage.files import output_path
from app.tools._async_runner import run_with_soft_cap
from app.tools._eta import status_payload_with_queue
from app.tools._schemas import TranscribeResult

Mode = Literal["fast", "offline"]
_MODE_TO_BACKEND = {"fast": "groq", "offline": "local"}
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
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def transcribe(
        source: str,
        mode: Mode = "fast",
        language: str = "",
        ctx: Context | None = None,
    ) -> TranscribeResult:
        """Transcribe spoken audio to text.

        ``source`` accepts:
        - a YouTube URL (any youtube.com / youtu.be / Shorts variant),
        - an HTTP(S) URL to an audio file,
        - an inline ``data:audio/...;base64,...`` payload (≤ 10 MB),
        - an ``upload_id`` returned by ``POST /upload`` (for larger files).

        ``mode`` picks the trade-off, both produce equally accurate text:
        - ``fast`` — paid cloud backend, finishes in seconds for typical inputs.
        - ``offline`` — free local CPU backend, slower (≈3 min audio per minute
          of compute) but never leaves the host. Pick this when the user wants
          off-cloud / private processing.

        ``language`` is an optional ISO code (``"pl"``, ``"en"`` …); leave
        empty for auto-detect.

        Returns a summary plus ``download.json`` / ``download.txt`` URLs and
        a 500-char ``preview``. Long YouTube videos and large files are
        handled automatically — captions, downsample, chunking, and a
        cloud-to-offline fallback. If a job won't fit in the soft cap,
        you'll get a ``queued`` status with a UUID and ``check_after_sec`` —
        poll ``get_job(uuid)``. On final failure, ``error.next_steps`` lists
        what to try.
        """
        backend = _MODE_TO_BACKEND[mode]

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

        budget = settings.default_wait_max_sec

        sem_backend = "faster_whisper" if backend == "local" else "groq"
        model_key = None
        model = ""

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
            params={"source": source, "language": language, "mode": mode},
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
            notes: list[str] = []
            try:
                await jobs_db.mark_started(uuid)
                await job_queue.start(uuid)
                start_mono = time.monotonic()
                async with semaphores.slot(sem_backend):
                    state.active_jobs += 1
                    try:
                        await reporter.report(1, 5, "resolving source")
                        with tempfile.TemporaryDirectory(prefix="audio_mcp_") as tmp:
                            tmp_path = Path(tmp)
                            resolved = await resolve_source(
                                source,
                                settings=settings,
                                work_dir=tmp_path,
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
                                audio_path = resolved.audio_path
                                if backend == "groq":
                                    audio_path = await compress_for_groq(
                                        audio_path, work_dir=tmp_path
                                    )
                                async with reporter.heartbeat(total=5, message="transcribing"):
                                    result = await _run_with_groq_fallback(
                                        backend=backend,
                                        audio_path=audio_path,
                                        language=language,
                                        model=model,
                                        settings=settings,
                                        notes=notes,
                                        log=log,
                                        stats=stats,
                                        jobs_db=jobs_db,
                                        job_queue=job_queue,
                                        uuid=uuid,
                                        model_key=model_key,
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
                if notes:
                    result_payload["notes"] = list(notes)
                await jobs_db.mark_done(uuid, result=result_payload)
                log.info("job_done", uuid=uuid, processing_sec=processing_sec)
                return result_payload
            except Exception as exc:
                error_payload = _build_error_payload(exc, notes)
                log.info("job_failed", uuid=uuid, error=error_payload)
                await jobs_db.mark_failed(uuid, error=json.dumps(error_payload))
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
        return TranscribeResult.model_validate(payload)


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


async def _run_with_groq_fallback(
    *,
    backend: str,
    audio_path: Path,
    language: str,
    model: str,
    settings,
    notes: list[str],
    log,
    stats,
    jobs_db,
    job_queue,
    uuid: str,
    model_key: str | None,
):
    """Invoke the requested backend; on Groq cloud failures, optionally fall
    back to local faster-whisper. Returns a TranscriptionResult.
    """
    tbackend = get_transcription_backend(backend, settings)
    try:
        return await tbackend.transcribe(
            audio_path,
            language=language or None,
            model=model or None,
        )
    except (APIStatusError, APIError) as exc:
        if backend != "groq" or not settings.groq_auto_fallback_local:
            raise
        reason = type(exc).__name__
        status_code = getattr(exc, "status_code", None)
        log.warning(
            "groq_failed_falling_back_to_local",
            uuid=uuid,
            reason=reason,
            status_code=status_code,
        )
        notes.append(
            f"groq failed ({reason}"
            + (f" status={status_code}" if status_code else "")
            + "): falling back to local faster-whisper"
        )
        local_backend = get_transcription_backend("local", settings)
        try:
            duration_hint = float(
                getattr(audio_path.stat(), "st_size", 0)
            )
        except OSError:
            duration_hint = 0.0
        if duration_hint > 0:
            refined = stats.predict(
                kind="transcribe",
                backend="local",
                model_key=model_key,
                size_proxy=duration_hint,
            )
            await jobs_db.update_size_proxy(
                uuid,
                size_proxy=duration_hint,
                predicted_processing_sec=refined.seconds,
            )
            await job_queue.update_predicted(uuid, refined.seconds)
        return await local_backend.transcribe(
            audio_path,
            language=language or None,
            model=model or None,
        )


def _stage_for(exc: Exception) -> str:
    if isinstance(exc, (APIStatusError, APIError)):
        return "groq_api"
    if "yt-dlp" in str(exc).lower() or "yt_dlp" in type(exc).__module__:
        return "yt_dlp"
    if "ffmpeg" in str(exc).lower():
        return "ffmpeg"
    return "transcribe"


def _build_error_payload(exc: Exception, notes: list[str]) -> dict:
    stage = _stage_for(exc)
    next_steps: list[str] = []
    if isinstance(exc, (APIStatusError, APIError)):
        next_steps = [
            "retry with mode='offline' (local CPU, slower but unbounded)",
            "shorten the source (e.g. split into ≤30 min segments)",
            "verify GROQ_API_KEY and your account quota",
        ]
    elif stage == "yt_dlp":
        next_steps = [
            "verify the YouTube URL is accessible (not age-restricted / region-locked)",
            "retry — yt-dlp is occasionally rate-limited by YouTube",
        ]
    else:
        next_steps = [
            "retry with mode='offline'",
            "inspect server logs for the failing stage",
        ]
    payload = {
        "message": str(exc),
        "exception": type(exc).__name__,
        "stage": stage,
        "next_steps": next_steps,
    }
    if notes:
        payload["notes"] = list(notes)
    return payload
