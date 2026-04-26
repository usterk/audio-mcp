"""Unit tests for app.tools._async_runner."""
from __future__ import annotations

import asyncio

import pytest

from app.tools._async_runner import run_with_soft_cap


@pytest.mark.asyncio
async def test_returns_sync_when_task_finishes_within_budget() -> None:
    async def quick() -> dict:
        await asyncio.sleep(0.01)
        return {"ok": True}

    async def on_timeout() -> dict:
        return {"queued": True}

    payload, was_async = await run_with_soft_cap(
        coro=quick(), wait_max_sec=1.0, on_timeout=on_timeout
    )
    assert payload == {"ok": True}
    assert was_async is False


@pytest.mark.asyncio
async def test_returns_async_payload_when_task_exceeds_budget() -> None:
    finished = asyncio.Event()

    async def slow() -> dict:
        try:
            await asyncio.sleep(2.0)
            return {"ok": True}
        finally:
            finished.set()

    async def on_timeout() -> dict:
        return {"queued": True, "uuid": "abc"}

    payload, was_async = await run_with_soft_cap(
        coro=slow(), wait_max_sec=0.1, on_timeout=on_timeout
    )
    assert payload == {"queued": True, "uuid": "abc"}
    assert was_async is True
    # Task is NOT cancelled — let it finish to prove it survived the timeout.
    await asyncio.wait_for(finished.wait(), timeout=3.0)


@pytest.mark.asyncio
async def test_shield_protects_task_from_outer_cancellation() -> None:
    """Even if the outer awaiter is cancelled, the inner task should keep going."""
    finished = asyncio.Event()

    async def slow() -> dict:
        try:
            await asyncio.sleep(0.5)
        finally:
            finished.set()
        return {"ok": True}

    async def on_timeout() -> dict:
        return {"queued": True}

    # Use task_set so we can keep the task alive after we cancel the outer call.
    task_set: set[asyncio.Task] = set()

    async def caller() -> tuple[dict, bool]:
        return await run_with_soft_cap(
            coro=slow(),
            wait_max_sec=10.0,
            on_timeout=on_timeout,
            task_set=task_set,
        )

    outer = asyncio.create_task(caller())
    await asyncio.sleep(0.05)
    outer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await outer
    # Inner task should still complete despite the outer cancellation.
    await asyncio.wait_for(finished.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_zero_budget_skips_wait_and_returns_async_immediately() -> None:
    started = asyncio.Event()

    async def long() -> dict:
        started.set()
        await asyncio.sleep(0.5)
        return {"ok": True}

    async def on_timeout() -> dict:
        return {"queued": True}

    payload, was_async = await run_with_soft_cap(
        coro=long(), wait_max_sec=0, on_timeout=on_timeout
    )
    assert was_async is True
    assert payload == {"queued": True}


@pytest.mark.asyncio
async def test_task_set_holds_strong_ref_then_releases() -> None:
    task_set: set[asyncio.Task] = set()

    async def quick() -> dict:
        return {"ok": True}

    async def on_timeout() -> dict:
        return {}

    payload, was_async = await run_with_soft_cap(
        coro=quick(), wait_max_sec=1.0, on_timeout=on_timeout, task_set=task_set
    )
    assert payload == {"ok": True}
    assert was_async is False
    # Give the discard callback time to fire
    await asyncio.sleep(0)
    assert len(task_set) == 0


@pytest.mark.asyncio
async def test_inner_exception_propagates_to_caller() -> None:
    async def boom() -> dict:
        raise RuntimeError("inner failure")

    async def on_timeout() -> dict:
        return {"queued": True}

    with pytest.raises(RuntimeError, match="inner failure"):
        await run_with_soft_cap(coro=boom(), wait_max_sec=1.0, on_timeout=on_timeout)
