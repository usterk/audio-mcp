"""Soft-cap helper used by transcribe/generate_audio MCP tools.

Spawns the inner job coroutine as a background task, waits up to
``wait_max_sec`` for it to finish *synchronously*, and otherwise returns
whatever ``on_timeout`` produces (typically a queued/running ETA payload).

``asyncio.shield`` ensures that timing out the outer wait does NOT cancel
the inner task — the job keeps running and writes its result to jobs.db
for later retrieval via ``get_job`` / ``list_recent_jobs``.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any


async def run_with_soft_cap(
    *,
    coro: Coroutine[Any, Any, dict[str, Any]],
    wait_max_sec: float,
    on_timeout: Callable[[], Awaitable[dict[str, Any]]],
    task_set: set[asyncio.Task[Any]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Run ``coro`` as a background task, return its result if it finishes
    in time, otherwise return ``on_timeout()`` (the task keeps running).

    Args:
        coro: The job's inner coroutine. Must handle its own failures
            (e.g. mark_failed in jobs.db). If it raises, the exception
            propagates to the caller — except when the soft cap fires
            first, in which case the exception surfaces later through
            jobs.db state.
        wait_max_sec: How long to wait synchronously. Values <= 0 skip
            waiting entirely.
        on_timeout: Async factory for the "still running" payload. Only
            called when the soft cap fires.
        task_set: Optional set to hold a strong ref to the task so it
            doesn't get garbage-collected while running detached. The
            task removes itself on completion.

    Returns:
        ``(payload, was_async)``. ``was_async=False`` means the inner
        coroutine completed within the budget; ``True`` means we returned
        the ``on_timeout`` payload and the task is still running.
    """
    task = asyncio.create_task(coro)
    if task_set is not None:
        task_set.add(task)
        task.add_done_callback(task_set.discard)

    if wait_max_sec <= 0:
        return await on_timeout(), True

    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=wait_max_sec)
        return result, False
    except asyncio.TimeoutError:
        return await on_timeout(), True
