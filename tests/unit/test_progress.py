"""Unit tests for app.progress."""
from __future__ import annotations

import asyncio

import pytest

from app.progress import ProgressReporter


class FakeCtx:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float, str]] = []
        self.meta_progress_token = "tok"

    async def report_progress(self, step: float, total: float, message: str = "") -> None:
        self.calls.append((step, total, message))


@pytest.mark.asyncio
async def test_report_forwards_to_ctx() -> None:
    ctx = FakeCtx()
    pr = ProgressReporter(ctx)
    await pr.report(1, 5, "step one")
    assert ctx.calls == [(1, 5, "step one")]


@pytest.mark.asyncio
async def test_heartbeat_emits_until_stopped() -> None:
    ctx = FakeCtx()
    pr = ProgressReporter(ctx, heartbeat_interval=0.02)
    async with pr.heartbeat(total=10, message="keepalive"):
        await asyncio.sleep(0.05)
    # At least one heartbeat was emitted; more is fine.
    assert len(ctx.calls) >= 1
    step, total, msg = ctx.calls[-1]
    assert total == 10
    assert msg == "keepalive"


@pytest.mark.asyncio
async def test_missing_ctx_is_noop() -> None:
    pr = ProgressReporter(None)
    await pr.report(1, 2, "x")
    async with pr.heartbeat(total=10, message="hb"):
        await asyncio.sleep(0.01)
