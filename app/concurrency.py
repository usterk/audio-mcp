"""Asyncio semaphore layout for the audio-mcp server."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass

CPU_BACKENDS: frozenset[str] = frozenset({"piper", "faster_whisper"})


@dataclass(frozen=True)
class ConcurrencyLimits:
    global_: int = 5
    cpu: int = 2


class Semaphores:
    def __init__(self, limits: ConcurrencyLimits) -> None:
        self._limits = limits
        self._global = asyncio.Semaphore(limits.global_)
        self._cpu: dict[str, asyncio.Semaphore] = {
            name: asyncio.Semaphore(limits.cpu) for name in CPU_BACKENDS
        }

    @staticmethod
    def is_cpu(backend: str) -> bool:
        return backend in CPU_BACKENDS

    @asynccontextmanager
    async def slot(self, backend: str):
        async with self._global:
            if backend in self._cpu:
                async with self._cpu[backend]:
                    yield
            else:
                yield
