"""GET /health."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

from app.version import VERSION

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    started_at: float = request.app.state.started_at
    active_jobs: int = getattr(request.app.state, "active_jobs", 0)
    backends_loaded: list[str] = list(getattr(request.app.state, "backends_loaded", []))
    return {
        "status": "ok",
        "version": VERSION,
        "uptime_sec": time.time() - started_at,
        "active_jobs": active_jobs,
        "backends_loaded": backends_loaded,
    }
