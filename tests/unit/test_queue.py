"""Unit tests for app.queue.JobQueue."""
from __future__ import annotations

import pytest

from app.queue import JobQueue


def _q(global_parallel: int = 5, cpu_parallel: int = 2) -> JobQueue:
    return JobQueue(global_parallel=global_parallel, cpu_parallel=cpu_parallel)


@pytest.mark.asyncio
async def test_submit_returns_snapshot_with_zero_wait_when_empty() -> None:
    q = _q()
    snap = await q.submit(uuid="a", sem_backend="groq", predicted_proc_sec=10.0)
    assert snap.global_position == 0
    assert snap.cpu_position == -1
    assert snap.predicted_wait_sec == pytest.approx(0.0)
    assert snap.status == "queued"


@pytest.mark.asyncio
async def test_groq_jobs_only_count_against_global() -> None:
    q = _q(global_parallel=2, cpu_parallel=2)
    await q.submit(uuid="a", sem_backend="groq", predicted_proc_sec=10.0)
    await q.submit(uuid="b", sem_backend="groq", predicted_proc_sec=10.0)
    snap = await q.submit(uuid="c", sem_backend="groq", predicted_proc_sec=10.0)
    assert snap.global_position == 2
    assert snap.cpu_position == -1
    # global wait = sum(20) / 2 = 10
    assert snap.predicted_wait_sec == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_cpu_backend_takes_max_of_global_and_cpu_wait() -> None:
    q = _q(global_parallel=5, cpu_parallel=1)
    # Two cpu jobs ahead (each 30s) and three groq jobs ahead (each 5s)
    for u in ("g1", "g2", "g3"):
        await q.submit(uuid=u, sem_backend="groq", predicted_proc_sec=5.0)
    for u in ("c1", "c2"):
        await q.submit(uuid=u, sem_backend="faster_whisper", predicted_proc_sec=30.0)
    snap = await q.submit(uuid="me", sem_backend="faster_whisper", predicted_proc_sec=30.0)
    # global wait: (5*3 + 30*2) / 5 = 75/5 = 15
    # cpu wait:    (30*2) / 1 = 60
    # max = 60
    assert snap.predicted_wait_sec == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_complete_removes_from_both_dimensions() -> None:
    q = _q()
    await q.submit(uuid="a", sem_backend="faster_whisper", predicted_proc_sec=20.0)
    await q.complete("a")
    snap = await q.snapshot("a")
    assert snap is None


@pytest.mark.asyncio
async def test_start_changes_status_but_keeps_in_queue_for_eta_math() -> None:
    q = _q()
    await q.submit(uuid="a", sem_backend="faster_whisper", predicted_proc_sec=10.0)
    await q.start("a")
    snap_a = await q.snapshot("a")
    assert snap_a is not None
    assert snap_a.status == "running"
    # A second job behind 'a' must still see it as ahead (slot occupied)
    await q.submit(uuid="b", sem_backend="faster_whisper", predicted_proc_sec=5.0)
    snap_b = await q.snapshot("b")
    assert snap_b is not None
    assert snap_b.global_position == 1


@pytest.mark.asyncio
async def test_update_predicted_changes_eta_for_followers() -> None:
    q = _q(global_parallel=1, cpu_parallel=1)
    await q.submit(uuid="a", sem_backend="faster_whisper", predicted_proc_sec=10.0)
    await q.submit(uuid="b", sem_backend="faster_whisper", predicted_proc_sec=10.0)
    snap_b_before = await q.snapshot("b")
    await q.update_predicted("a", 60.0)
    snap_b_after = await q.snapshot("b")
    assert snap_b_after.predicted_wait_sec > snap_b_before.predicted_wait_sec
    assert snap_b_after.predicted_wait_sec == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_predicted_wait_for_new_does_not_modify_state() -> None:
    q = _q(global_parallel=2, cpu_parallel=2)
    await q.submit(uuid="a", sem_backend="groq", predicted_proc_sec=20.0)
    wait = await q.predicted_wait_for_new(sem_backend="groq", predicted_proc_sec=10.0)
    assert wait == pytest.approx(10.0)  # 20/2
    # Still only one entry, queue unchanged
    snap = await q.snapshot("a")
    assert snap is not None
    assert snap.global_position == 0


@pytest.mark.asyncio
async def test_unknown_uuid_returns_none() -> None:
    q = _q()
    assert await q.snapshot("nope") is None


def test_construct_rejects_zero_parallelism() -> None:
    with pytest.raises(ValueError):
        JobQueue(global_parallel=0, cpu_parallel=2)
    with pytest.raises(ValueError):
        JobQueue(global_parallel=5, cpu_parallel=0)


def test_is_cpu_backend_check() -> None:
    q = _q()
    assert q.is_cpu_backend("faster_whisper") is True
    assert q.is_cpu_backend("piper") is True
    assert q.is_cpu_backend("groq") is False
