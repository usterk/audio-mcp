"""Progress notification and heartbeat helpers for long-running tools."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol


class _CtxLike(Protocol):
    async def report_progress(self, step: float, total: float, message: str = "") -> None: ...


class ProgressReporter:
    """Wraps an MCP Context to emit progress and idle heartbeats.

    If ``ctx`` is ``None``, every operation is a no-op so tools can be
    exercised in tests without a real Context.
    """

    def __init__(self, ctx: _CtxLike | None, *, heartbeat_interval: float = 15.0) -> None:
        self._ctx = ctx
        self._heartbeat_interval = heartbeat_interval

    async def report(self, step: float, total: float, message: str = "") -> None:
        if self._ctx is None:
            return
        try:
            await self._ctx.report_progress(step, total, message)
        except Exception:
            return

    @asynccontextmanager
    async def heartbeat(self, *, total: float, message: str) -> AsyncIterator[None]:
        if self._ctx is None:
            yield
            return

        stop = asyncio.Event()

        async def _loop() -> None:
            tick = 0
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._heartbeat_interval)
                    return
                except TimeoutError:
                    tick += 1
                    await self.report(tick, total, message)

        task = asyncio.create_task(_loop())
        try:
            yield
        finally:
            stop.set()
            await asyncio.gather(task, return_exceptions=True)
