"""Public output schemas for MCP tools.

The agent reads ``output_schema`` from ``tools/list`` to know what fields
it can expect back from a tool — so we model what the tools return as
typed Pydantic objects rather than loose ``dict``. ``extra="allow"`` so
that backwards-compatibility with older clients (or transitional fields
like ``message`` for queued payloads) does not break callers.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class _ToolModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class TranscribeResult(_ToolModel):
    uuid: str
    status: Literal["queued", "running", "done", "failed"]
    was_async: bool = False
    summary: str | None = None
    duration_sec: float | None = None
    language: str | None = None
    segments_count: int | None = None
    download: dict[str, str] | None = None
    preview: str | None = None
    processing_sec: float | None = None
    predicted_processing_sec: float | None = None
    size_proxy: float | None = None
    model_key: str | None = None
    notes: list[str] | None = None
    # Fields used when status is queued/running:
    elapsed_sec: float | None = None
    eta_remaining_sec: float | None = None
    check_after_sec: float | None = None
    queue_position: int | None = None
    message: str | None = None


class GenerateAudioResult(_ToolModel):
    uuid: str
    status: Literal["queued", "running", "done", "failed"]
    was_async: bool = False
    duration_sec: float | None = None
    bytes: int | None = None
    voice: str | None = None
    backend: str | None = None
    model: str | None = None
    format: str | None = None
    download: dict[str, str] | None = None
    normalized_text: str | None = None
    processing_sec: float | None = None
    predicted_processing_sec: float | None = None
    size_proxy: float | None = None
    model_key: str | None = None
    # Fields used when status is queued/running:
    elapsed_sec: float | None = None
    eta_remaining_sec: float | None = None
    check_after_sec: float | None = None
    queue_position: int | None = None
    message: str | None = None


class JobInfo(_ToolModel):
    """Status snapshot of a single job — used by `get_job` and `list_recent_jobs`."""

    uuid: str
    status: Literal["queued", "running", "done", "failed"] | None = None
    kind: str | None = None
    backend: str | None = None
    model_key: str | None = None
    created_at: int | None = None
    started_at: int | None = None
    finished_at: int | None = None
    size_proxy: float | None = None
    predicted_processing_sec: float | None = None
    processing_sec: float | None = None
    elapsed_sec: float | None = None
    eta_remaining_sec: float | None = None
    check_after_sec: float | None = None
    queue_position: int | None = None
    download: dict[str, str] | None = None
    error: str | dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class Voice(_ToolModel):
    id: str
    name: str | None = None
    language: str | None = None
    gender: str | None = None
    tags: list[str] | None = None
