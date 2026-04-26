"""Shared helpers that turn a jobs.db row + queue snapshot into the
status-payload fields the MCP tools surface to agents."""
from __future__ import annotations

import contextlib
import json
import math
import time
from typing import Any

from app.queue import JobQueue, QueueSnapshot


def _download_for(kind: str, uuid: str, base_url: str) -> dict[str, str]:
    base = base_url.rstrip("/")
    if kind == "transcribe":
        return {
            "json": f"{base}/jobs/{uuid}/transcription.json",
            "txt": f"{base}/jobs/{uuid}/transcription.txt",
        }
    return {"audio": f"{base}/jobs/{uuid}/audio.mp3"}


def _eta_remaining_sec(
    *,
    status: str,
    started_at: int | None,
    predicted_processing_sec: float | None,
    queue_snap: QueueSnapshot | None,
    now: float,
) -> float | None:
    """Best-effort seconds-until-finish for an in-flight job.

    Returns None for terminal statuses (done/failed). For queued jobs we
    add the queue wait. For running jobs we discount the elapsed time
    against the predicted processing time, clamped to >= 0 so agents
    never see a negative ETA.
    """
    if status in ("done", "failed"):
        return None

    proc = float(predicted_processing_sec) if predicted_processing_sec is not None else 0.0
    wait = queue_snap.predicted_wait_sec if queue_snap is not None else 0.0

    if status == "queued":
        return wait + proc

    # running
    if started_at is None:
        return proc
    elapsed = max(0.0, now - float(started_at))
    return max(0.0, proc - elapsed)


def status_payload(
    *,
    job_row: dict[str, Any],
    queue: JobQueue | None,
    base_url: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Build the agent-facing status dict for a single job.

    Includes ETA fields when the job is queued/running, processing_sec
    when it has started, and the result/error when terminal.
    """
    now = now if now is not None else time.time()
    uuid = job_row["uuid"]
    status = job_row["status"]
    started_at = job_row.get("started_at")
    finished_at = job_row.get("finished_at")
    predicted = job_row.get("predicted_processing_sec")

    queue_snap: QueueSnapshot | None = None
    if queue is not None and status in ("queued", "running"):
        # snapshot is async; callers that have an event loop should resolve it
        # themselves and pass it via params. For callers that already have it,
        # see status_payload_with_snapshot below.
        queue_snap = None  # populated by status_payload_with_snapshot

    elapsed_sec: float | None = None
    if started_at is not None:
        end = float(finished_at) if finished_at is not None else now
        elapsed_sec = max(0.0, end - float(started_at))

    eta = _eta_remaining_sec(
        status=status,
        started_at=started_at,
        predicted_processing_sec=predicted,
        queue_snap=queue_snap,
        now=now,
    )
    check_after_sec: float | None = None
    if eta is not None and eta > 0:
        check_after_sec = math.ceil(eta + 5)

    payload: dict[str, Any] = {
        "uuid": uuid,
        "kind": job_row["kind"],
        "backend": job_row["backend"],
        "model_key": job_row.get("model_key"),
        "status": status,
        "created_at": job_row.get("created_at"),
        "started_at": started_at,
        "finished_at": finished_at,
        "size_proxy": job_row.get("size_proxy"),
        "predicted_processing_sec": predicted,
        "elapsed_sec": elapsed_sec,
        "eta_remaining_sec": eta,
        "check_after_sec": check_after_sec,
        "download": _download_for(job_row["kind"], uuid, base_url),
        "error": job_row.get("error"),
    }
    if status == "done" and job_row.get("result_json"):
        with contextlib.suppress(TypeError, ValueError):
            payload["result"] = json.loads(job_row["result_json"])
    return payload


async def status_payload_with_queue(
    *,
    job_row: dict[str, Any],
    queue: JobQueue | None,
    base_url: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Async wrapper that resolves the queue snapshot for in-flight jobs."""
    payload = status_payload(job_row=job_row, queue=queue, base_url=base_url, now=now)
    if queue is None or job_row["status"] not in ("queued", "running"):
        return payload
    snap = await queue.snapshot(job_row["uuid"])
    if snap is None:
        return payload
    payload["queue_position"] = snap.global_position
    if snap.cpu_position >= 0:
        payload["cpu_queue_position"] = snap.cpu_position
    payload["predicted_wait_sec"] = snap.predicted_wait_sec
    eta = _eta_remaining_sec(
        status=job_row["status"],
        started_at=job_row.get("started_at"),
        predicted_processing_sec=job_row.get("predicted_processing_sec"),
        queue_snap=snap,
        now=now if now is not None else time.time(),
    )
    payload["eta_remaining_sec"] = eta
    payload["check_after_sec"] = math.ceil(eta + 5) if eta is not None and eta > 0 else None
    return payload
