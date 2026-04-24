"""Unit tests for app.concurrency."""
from __future__ import annotations

import asyncio

import pytest

from app.concurrency import ConcurrencyLimits, Semaphores


@pytest.mark.asyncio
async def test_global_slot_caps_parallel_callers() -> None:
    sems = Semaphores(ConcurrencyLimits(global_=2, cpu=4))
    live = 0
    peak = 0

    async def worker() -> None:
        nonlocal live, peak
        async with sems.slot("groq"):
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1

    await asyncio.gather(*(worker() for _ in range(6)))
    assert peak == 2


@pytest.mark.asyncio
async def test_cpu_backend_has_tighter_limit() -> None:
    sems = Semaphores(ConcurrencyLimits(global_=10, cpu=1))
    live = 0
    peak = 0

    async def worker() -> None:
        nonlocal live, peak
        async with sems.slot("piper"):
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0.02)
            live -= 1

    await asyncio.gather(*(worker() for _ in range(5)))
    assert peak == 1


def test_is_cpu_backend() -> None:
    sems = Semaphores(ConcurrencyLimits(global_=5, cpu=2))
    assert sems.is_cpu("piper")
    assert sems.is_cpu("faster_whisper")
    assert not sems.is_cpu("groq")
    assert not sems.is_cpu("gcloud")
    assert not sems.is_cpu("openai")
