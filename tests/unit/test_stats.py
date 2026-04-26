"""Unit tests for app.stats.RollingStats."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.stats import RollingStats
from app.storage.jobs_db import JobsDB


def test_predict_uses_default_when_no_samples() -> None:
    stats = RollingStats()
    pred = stats.predict(kind="transcribe", backend="local", model_key=None, size_proxy=60.0)
    assert pred.is_default is True
    assert pred.samples_used == 0
    assert pred.seconds == pytest.approx(0.25 * 60.0)


def test_predict_uses_groq_default_separately_from_local() -> None:
    stats = RollingStats()
    p_groq = stats.predict(kind="transcribe", backend="groq", model_key=None, size_proxy=600.0)
    p_local = stats.predict(kind="transcribe", backend="local", model_key=None, size_proxy=600.0)
    # groq should be much faster than local in cold-start defaults
    assert p_groq.seconds < p_local.seconds


def test_record_then_predict_uses_median() -> None:
    stats = RollingStats()
    # 5 samples at 0.1, 0.2, 0.3, 0.4, 0.5 RTF on 100s of audio
    for sec in (10.0, 20.0, 30.0, 40.0, 50.0):
        stats.record(
            kind="transcribe", backend="local", model_key="small",
            size_proxy=100.0, processing_sec=sec,
        )
    pred = stats.predict(kind="transcribe", backend="local", model_key="small", size_proxy=200.0)
    assert pred.is_default is False
    assert pred.samples_used == 5
    # median rate is 0.3, applied to 200s → 60s
    assert pred.seconds == pytest.approx(60.0)


def test_window_evicts_oldest() -> None:
    stats = RollingStats(window=3)
    # First 3 fast samples
    for _ in range(3):
        stats.record(
            kind="transcribe", backend="local", model_key=None,
            size_proxy=100.0, processing_sec=1.0,
        )
    # Then 3 slow samples push the fast ones out
    for _ in range(3):
        stats.record(
            kind="transcribe", backend="local", model_key=None,
            size_proxy=100.0, processing_sec=100.0,
        )
    pred = stats.predict(kind="transcribe", backend="local", model_key=None, size_proxy=100.0)
    assert pred.samples_used == 3
    # Median of three 1.0-rate samples → 100s
    assert pred.seconds == pytest.approx(100.0)


def test_keys_are_isolated_by_kind_backend_model() -> None:
    stats = RollingStats()
    stats.record(
        kind="transcribe", backend="local", model_key="small",
        size_proxy=100.0, processing_sec=10.0,
    )
    p_other_model = stats.predict(
        kind="transcribe", backend="local", model_key="large", size_proxy=100.0
    )
    p_other_backend = stats.predict(
        kind="transcribe", backend="groq", model_key="small", size_proxy=100.0
    )
    p_other_kind = stats.predict(
        kind="generate_audio", backend="local", model_key="small", size_proxy=100.0
    )
    assert p_other_model.is_default is True
    assert p_other_backend.is_default is True
    assert p_other_kind.is_default is True


def test_empty_model_key_normalised_to_none() -> None:
    stats = RollingStats()
    stats.record(
        kind="transcribe", backend="groq", model_key="",
        size_proxy=10.0, processing_sec=1.0,
    )
    p_via_none = stats.predict(
        kind="transcribe", backend="groq", model_key=None, size_proxy=10.0
    )
    assert p_via_none.is_default is False
    assert p_via_none.samples_used == 1


def test_zero_size_short_circuits_to_zero() -> None:
    stats = RollingStats()
    pred = stats.predict(kind="generate_audio", backend="piper", model_key="g", size_proxy=0)
    assert pred.seconds == 0.0
    assert pred.is_default is False


def test_record_ignores_invalid_inputs() -> None:
    stats = RollingStats()
    stats.record(
        kind="transcribe", backend="local", model_key=None,
        size_proxy=0, processing_sec=10.0,
    )
    stats.record(
        kind="transcribe", backend="local", model_key=None,
        size_proxy=10.0, processing_sec=-1.0,
    )
    pred = stats.predict(kind="transcribe", backend="local", model_key=None, size_proxy=10.0)
    assert pred.is_default is True


def test_snapshot_returns_per_key_stats() -> None:
    stats = RollingStats()
    stats.record(
        kind="transcribe", backend="groq", model_key=None,
        size_proxy=100.0, processing_sec=2.0,
    )
    stats.record(
        kind="transcribe", backend="local", model_key="small",
        size_proxy=100.0, processing_sec=20.0,
    )
    snap = stats.snapshot()
    assert ("transcribe", "groq", None) in snap
    assert ("transcribe", "local", "small") in snap
    assert snap[("transcribe", "local", "small")]["samples"] == 1


@pytest.mark.asyncio
async def test_prime_from_db_loads_recent_done_jobs(tmp_path: Path) -> None:
    db = JobsDB(tmp_path / "jobs.db")
    await db.init()
    # A done job we want to pick up
    await db.create_job(
        uuid="d1", kind="transcribe", backend="local", params={}, model_key="small"
    )
    await db.mark_started("d1")
    await asyncio.sleep(1.05)  # ensure finished_at - started_at >= 1
    await db.update_size_proxy("d1", size_proxy=60.0)
    await db.mark_done("d1", result={})
    # A failed job that must be skipped
    await db.create_job(
        uuid="f1", kind="transcribe", backend="local", params={}, model_key="small"
    )
    await db.mark_started("f1")
    await db.mark_failed("f1", error="x")

    stats = RollingStats()
    await stats.prime_from_db(db)
    pred = stats.predict(
        kind="transcribe", backend="local", model_key="small", size_proxy=60.0
    )
    assert pred.is_default is False
    assert pred.samples_used == 1
