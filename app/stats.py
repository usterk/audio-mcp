"""Rolling per-(kind, backend, model_key) processing-rate statistics.

For ``transcribe`` the unit is "real-time factor" (processing_sec per audio_sec).
For ``generate_audio`` it is "seconds per character" of normalized text.

The same shape works for both because callers supply the right ``size_proxy``
(audio duration or character count) at record/predict time.

Statistics are kept in-memory only. Hot rate updates happen synchronously
on ``record``; we don't try to persist between restarts — at startup the
caller invokes :py:meth:`RollingStats.prime_from_db` to refill from the
last N done jobs in jobs.db.
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.storage.jobs_db import JobsDB


# Cold-start defaults. Conservative — over-predicting nudges marginal jobs
# into the async branch which is the safer side.
_DEFAULTS_TRANSCRIBE: dict[str, float] = {
    "groq": 0.02,
    "local": 0.25,
}
_DEFAULTS_TTS: dict[str, float] = {
    "piper": 0.001,
    "gcloud": 0.003,
    "openai": 0.02,
    "gemini": 0.02,
}
_DEFAULT_FALLBACK = 0.5  # if backend not recognised at all (very pessimistic)


@dataclass(frozen=True, slots=True)
class Prediction:
    seconds: float
    samples_used: int
    is_default: bool


def _default_rate(kind: str, backend: str) -> float:
    if kind == "transcribe":
        return _DEFAULTS_TRANSCRIBE.get(backend, _DEFAULT_FALLBACK)
    if kind == "generate_audio":
        return _DEFAULTS_TTS.get(backend, _DEFAULT_FALLBACK)
    return _DEFAULT_FALLBACK


class RollingStats:
    """Median rolling-window predictor keyed by (kind, backend, model_key)."""

    def __init__(self, *, window: int = 20) -> None:
        self._window = window
        self._samples: dict[tuple[str, str, str | None], deque[float]] = {}

    @staticmethod
    def _norm_model(model_key: str | None) -> str | None:
        return model_key or None

    def record(
        self,
        *,
        kind: str,
        backend: str,
        model_key: str | None,
        size_proxy: float,
        processing_sec: float,
    ) -> None:
        if size_proxy <= 0 or processing_sec < 0:
            return
        rate = processing_sec / size_proxy
        key = (kind, backend, self._norm_model(model_key))
        bucket = self._samples.get(key)
        if bucket is None:
            bucket = deque(maxlen=self._window)
            self._samples[key] = bucket
        bucket.append(rate)

    def predict(
        self,
        *,
        kind: str,
        backend: str,
        model_key: str | None,
        size_proxy: float,
    ) -> Prediction:
        if size_proxy <= 0:
            return Prediction(seconds=0.0, samples_used=0, is_default=False)
        key = (kind, backend, self._norm_model(model_key))
        bucket = self._samples.get(key)
        if bucket and len(bucket) > 0:
            rate = statistics.median(bucket)
            return Prediction(
                seconds=rate * size_proxy,
                samples_used=len(bucket),
                is_default=False,
            )
        return Prediction(
            seconds=_default_rate(kind, backend) * size_proxy,
            samples_used=0,
            is_default=True,
        )

    def snapshot(self) -> dict[tuple[str, str, str | None], dict[str, float | int]]:
        """Return a copy of current per-key median + sample count for diagnostics."""
        out: dict[tuple[str, str, str | None], dict[str, float | int]] = {}
        for key, bucket in self._samples.items():
            if not bucket:
                continue
            out[key] = {
                "median_rate": statistics.median(bucket),
                "samples": len(bucket),
            }
        return out

    async def prime_from_db(self, jobs_db: JobsDB) -> None:
        """Replay recent done jobs into the in-memory window.

        Walks the most recent done jobs per distinct (kind, backend, model_key)
        seen in the last ``window`` rows. Non-positive size_proxy or missing
        timestamps are skipped.
        """
        recent = await jobs_db.list_recent(limit=200)
        # Walk newest-first, but append in chronological order so eviction
        # behaves as if we recorded them as they happened.
        in_chrono = list(reversed(recent))
        for row in in_chrono:
            if row.get("status") != "done":
                continue
            size_proxy = row.get("size_proxy")
            started_at = row.get("started_at")
            finished_at = row.get("finished_at")
            if size_proxy is None or started_at is None or finished_at is None:
                continue
            processing_sec = float(finished_at) - float(started_at)
            if processing_sec < 0:
                continue
            self.record(
                kind=row["kind"],
                backend=row["backend"],
                model_key=row.get("model_key"),
                size_proxy=float(size_proxy),
                processing_sec=processing_sec,
            )
