"""In-memory job queue tracking ETA across two semaphore dimensions.

Every audio-mcp job competes for a global slot (default 5). CPU backends
(``faster_whisper``, ``piper``) additionally compete for a per-backend CPU
slot (default 2). ``asyncio.Semaphore`` exposes no introspection, so this
queue is the source of truth for "how many jobs are ahead of mine and
roughly when can I start".

State is in-process only and not persisted. After a restart the queue
starts empty and the lifespan sweep marks any rows that were still
``queued``/``running`` in jobs.db as failed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class QueueEntry:
    uuid: str
    sem_backend: str
    predicted_proc_sec: float
    status: str = field(default="queued")  # 'queued' | 'running'


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    """Per-job view used to compute ETA payloads."""

    uuid: str
    sem_backend: str
    status: str
    global_position: int
    cpu_position: int  # -1 when sem_backend is not CPU-bound
    predicted_proc_sec: float
    predicted_wait_sec: float


class JobQueue:
    """Tracks queued/running jobs and computes wait estimates.

    Wait estimate model:
      - global_wait = sum(predicted_proc_sec of all entries ahead) / global_parallel
      - cpu_wait    = sum(predicted_proc_sec of cpu entries ahead)  / cpu_parallel
      - effective wait = max(global_wait, cpu_wait)

    "Ahead" here includes currently-running entries — they hold slots until
    they finish. That mildly overestimates because running jobs are partway
    through, but it's a safe-side error: predicting a longer wait nudges
    callers into the async branch which is the intended outcome.
    """

    def __init__(
        self,
        *,
        global_parallel: int,
        cpu_parallel: int,
        cpu_backends: frozenset[str] = frozenset({"faster_whisper", "piper"}),
    ) -> None:
        if global_parallel < 1 or cpu_parallel < 1:
            raise ValueError("parallel limits must be >= 1")
        self._global_parallel = global_parallel
        self._cpu_parallel = cpu_parallel
        self._cpu_backends = cpu_backends
        self._global: list[QueueEntry] = []
        self._cpu: dict[str, list[QueueEntry]] = {b: [] for b in cpu_backends}
        self._lock = asyncio.Lock()

    def is_cpu_backend(self, sem_backend: str) -> bool:
        return sem_backend in self._cpu_backends

    async def submit(
        self, *, uuid: str, sem_backend: str, predicted_proc_sec: float
    ) -> QueueSnapshot:
        async with self._lock:
            entry = QueueEntry(
                uuid=uuid,
                sem_backend=sem_backend,
                predicted_proc_sec=max(0.0, predicted_proc_sec),
                status="queued",
            )
            self._global.append(entry)
            if sem_backend in self._cpu:
                self._cpu[sem_backend].append(entry)
            return self._snapshot_locked(uuid)

    async def start(self, uuid: str) -> None:
        async with self._lock:
            for entry in self._global:
                if entry.uuid == uuid:
                    entry.status = "running"
                    return

    async def complete(self, uuid: str) -> None:
        async with self._lock:
            self._global = [e for e in self._global if e.uuid != uuid]
            for backend, lst in self._cpu.items():
                self._cpu[backend] = [e for e in lst if e.uuid != uuid]

    async def update_predicted(self, uuid: str, predicted_proc_sec: float) -> None:
        async with self._lock:
            for entry in self._global:
                if entry.uuid == uuid:
                    entry.predicted_proc_sec = max(0.0, predicted_proc_sec)
                    return

    async def snapshot(self, uuid: str) -> QueueSnapshot | None:
        async with self._lock:
            return self._snapshot_locked(uuid)

    async def predicted_wait_for_new(
        self, *, sem_backend: str, predicted_proc_sec: float
    ) -> float:
        """Estimate wait if we were to submit right now (without actually submitting)."""
        async with self._lock:
            global_wait = (
                sum(e.predicted_proc_sec for e in self._global) / self._global_parallel
            )
            if sem_backend in self._cpu:
                cpu_wait = (
                    sum(e.predicted_proc_sec for e in self._cpu[sem_backend])
                    / self._cpu_parallel
                )
            else:
                cpu_wait = 0.0
            _ = predicted_proc_sec  # not used here; reserved for fancier estimators
            return max(global_wait, cpu_wait)

    def _snapshot_locked(self, uuid: str) -> QueueSnapshot | None:
        try:
            global_idx = next(i for i, e in enumerate(self._global) if e.uuid == uuid)
        except StopIteration:
            return None
        entry = self._global[global_idx]
        ahead_global = self._global[:global_idx]
        global_wait = (
            sum(e.predicted_proc_sec for e in ahead_global) / self._global_parallel
        )
        if entry.sem_backend in self._cpu:
            cpu_list = self._cpu[entry.sem_backend]
            try:
                cpu_idx = next(i for i, e in enumerate(cpu_list) if e.uuid == uuid)
            except StopIteration:
                cpu_idx = -1
                cpu_wait = 0.0
            else:
                ahead_cpu = cpu_list[:cpu_idx]
                cpu_wait = (
                    sum(e.predicted_proc_sec for e in ahead_cpu) / self._cpu_parallel
                )
        else:
            cpu_idx = -1
            cpu_wait = 0.0
        return QueueSnapshot(
            uuid=uuid,
            sem_backend=entry.sem_backend,
            status=entry.status,
            global_position=global_idx,
            cpu_position=cpu_idx,
            predicted_proc_sec=entry.predicted_proc_sec,
            predicted_wait_sec=max(global_wait, cpu_wait),
        )
