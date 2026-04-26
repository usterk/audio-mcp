"""`generate_audio` MCP tool."""
from __future__ import annotations

import time
import uuid as uuidlib

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request

from app.backends import get_tts_backend
from app.logging_setup import get_logger
from app.preprocessing import normalize_text
from app.progress import ProgressReporter
from app.storage.files import output_path
from app.tools._async_runner import run_with_soft_cap
from app.tools._eta import status_payload_with_queue

VALID_BACKENDS = ("piper", "gcloud", "openai", "gemini")
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
        wait_max_sec: int | None = None,
        ctx: Context | None = None,
    ) -> dict:
        """Generate an audio file from text.

        Backends: ``piper`` (default, local CPU, free), ``gcloud``
        (Google Cloud TTS Standard), ``openai`` (gpt-4o-mini-tts, supports
        a ``style`` instruction). Text preprocessing (``normalize='basic'``)
        replaces URLs, long hashes and Polish acronyms with phonetic
        spellings before sending to the backend. Use ``normalize='none'``
        to bypass preprocessing entirely.

        ``wait_max_sec`` (default ``settings.default_wait_max_sec`` = 50)
        bounds how long the call may block. If the predicted total time
        exceeds the budget, the response returns immediately with status
        ``queued``/``running``, the job UUID, and ``check_after_sec`` —
        poll ``get_job(uuid)`` after that many seconds.
        """
        if backend not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}")
        if format not in VALID_FORMATS:
            raise ValueError(f"format must be one of {VALID_FORMATS}")
        if normalize not in VALID_NORMALIZE:
            raise ValueError(f"normalize must be one of {VALID_NORMALIZE}")

        request = get_http_request()
        app = request.app
        state = app.state
        settings = state.settings
        jobs_db = state.jobs_db
        semaphores = state.semaphores
        job_queue = state.job_queue
        stats = state.stats
        background_tasks = state.background_tasks

        budget = wait_max_sec if wait_max_sec is not None else settings.default_wait_max_sec

        # Normalise up-front so size_proxy / predicted ETA are accurate.
        tts = get_tts_backend(backend, settings)
        effective_mode = normalize
        if tts.normalizes_own_text and normalize == "basic":
            effective_mode = "none"
        normalized = normalize_text(text, language=language, mode=effective_mode)
        size_proxy = float(len(normalized))
        model_key = voice or model or None

        prediction = stats.predict(
            kind="generate_audio",
            backend=backend,
            model_key=model_key,
            size_proxy=size_proxy,
        )
        predicted_proc_sec = prediction.seconds

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
            size_proxy=size_proxy,
            predicted_processing_sec=predicted_proc_sec,
            model_key=model_key,
        )
        await job_queue.submit(
            uuid=uuid, sem_backend=backend, predicted_proc_sec=predicted_proc_sec
        )
        log = get_logger(__name__)
        log.info(
            "job_start",
            uuid=uuid,
            kind="generate_audio",
            backend=backend,
            size_proxy=size_proxy,
            predicted_processing_sec=predicted_proc_sec,
        )

        reporter = ProgressReporter(ctx)
        out_path = output_path(settings.data_dir, uuid, "audio", format)

        async def _do_work() -> dict:
            try:
                await jobs_db.mark_started(uuid)
                await job_queue.start(uuid)
                start_mono = time.monotonic()
                async with semaphores.slot(backend):
                    state.active_jobs += 1
                    try:
                        await reporter.report(1, 3, "synthesising audio")
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
                        state.active_jobs -= 1
                processing_sec = time.monotonic() - start_mono
                stats.record(
                    kind="generate_audio",
                    backend=backend,
                    model_key=model_key,
                    size_proxy=size_proxy,
                    processing_sec=processing_sec,
                )
                response = {
                    "uuid": uuid,
                    "status": "done",
                    "was_async": False,
                    "duration_sec": result.duration_sec,
                    "bytes": result.bytes,
                    "voice": result.voice,
                    "backend": result.backend,
                    "model": result.model,
                    "format": result.format,
                    "download": {"audio": _download_url(settings, uuid, format)},
                    "normalized_text": normalized,
                    "processing_sec": processing_sec,
                    "predicted_processing_sec": predicted_proc_sec,
                    "size_proxy": size_proxy,
                    "model_key": model_key,
                }
                await jobs_db.mark_done(uuid, result=response)
                log.info("job_done", uuid=uuid, processing_sec=processing_sec)
                await reporter.report(3, 3, "done")
                return response
            except Exception as exc:
                log.info("job_failed", uuid=uuid, error=str(exc))
                await jobs_db.mark_failed(uuid, error=str(exc))
                raise
            finally:
                await job_queue.complete(uuid)

        async def _async_payload() -> dict:
            row = await jobs_db.get_job(uuid)
            if row is None:
                # Should not happen; create_job ran above.
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
            payload["message"] = (
                f"Audio generation will take ~{prediction.seconds:.1f}s. "
                f"Call get_job('{uuid}') after {payload.get('check_after_sec') or 5}s."
            )
            return payload

        # If predicted total clearly exceeds the budget, don't burn it waiting.
        # job_queue already has us in the queue, so its predicted_wait_sec
        # accounts for in-flight jobs ahead of us.
        snap = await job_queue.snapshot(uuid)
        predicted_wait = snap.predicted_wait_sec if snap is not None else 0.0
        predicted_total = predicted_wait + predicted_proc_sec
        effective_wait = budget if predicted_total <= budget else 0

        payload, _ = await run_with_soft_cap(
            coro=_do_work(),
            wait_max_sec=effective_wait,
            on_timeout=_async_payload,
            task_set=background_tasks,
        )
        return payload
