"""FastAPI app factory with FastMCP mounted at /mcp."""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from app.concurrency import ConcurrencyLimits, Semaphores
from app.config import Settings, get_settings
from app.http import downloads as downloads_router
from app.http import health as health_router
from app.http import landing as landing_router
from app.http import upload as upload_router
from app.logging_setup import configure_logging, get_logger
from app.mcp_server import create_mcp
from app.queue import JobQueue
from app.stats import RollingStats
from app.storage.files import remove_expired_uploads
from app.storage.jobs_db import JobsDB


async def _sweep_unfinished_jobs(jobs_db: JobsDB) -> int:
    """Mark any queued/running rows from a previous process as failed.

    The in-memory queue and background tasks don't survive a restart, so
    rows still flagged 'queued' or 'running' are orphaned. Failing them
    explicitly keeps stats clean (failed rows are excluded from RollingStats)
    and gives clients a deterministic terminal state.
    """
    log = get_logger(__name__)
    rows = await jobs_db.list_unfinished()
    for row in rows:
        await jobs_db.mark_failed(row["uuid"], error="server_restart")
    if rows:
        log.info("restart_sweep", marked_failed=len(rows))
    return len(rows)


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()

    mcp = create_mcp()
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_dirs()
        async with mcp_app.lifespan(app):
            app.state.started_at = time.time()
            app.state.settings = settings
            app.state.mcp = mcp
            jobs_db = JobsDB(settings.data_dir / "jobs.db")
            await jobs_db.init()
            await _sweep_unfinished_jobs(jobs_db)
            app.state.jobs_db = jobs_db
            semaphores = Semaphores(
                ConcurrencyLimits(
                    global_=settings.global_concurrency,
                    cpu=settings.cpu_backend_concurrency,
                )
            )
            app.state.semaphores = semaphores
            app.state.active_jobs = 0
            backends_loaded: list[str] = []
            app.state.backends_loaded = backends_loaded

            job_queue = JobQueue(
                global_parallel=settings.global_concurrency,
                cpu_parallel=settings.cpu_backend_concurrency,
            )
            app.state.job_queue = job_queue

            stats = RollingStats(window=settings.stats_window)
            await stats.prime_from_db(jobs_db)
            app.state.stats = stats

            background_tasks: set[asyncio.Task[Any]] = set()
            app.state.background_tasks = background_tasks

            # request.app inside the /mcp sub-app resolves to mcp_app, not the root
            # FastAPI app, so tools reading request.app.state need these attributes here.
            mcp_app.state.settings = settings
            mcp_app.state.jobs_db = jobs_db
            mcp_app.state.semaphores = semaphores
            mcp_app.state.active_jobs = 0
            mcp_app.state.backends_loaded = backends_loaded
            mcp_app.state.job_queue = job_queue
            mcp_app.state.stats = stats
            mcp_app.state.background_tasks = background_tasks

            scheduler = AsyncIOScheduler()

            async def _tick() -> None:
                n_files = remove_expired_uploads(settings.data_dir, ttl_seconds=settings.upload_ttl_seconds)
                n_rows = await app.state.jobs_db.delete_expired_uploads()
                get_logger(__name__).info("upload_cleanup", files=n_files, rows=n_rows)

            scheduler.add_job(_tick, "interval", minutes=60, id="upload_cleanup")
            scheduler.start()
            app.state.scheduler = scheduler

            try:
                yield
            finally:
                scheduler.shutdown(wait=False)
                in_flight = [t for t in background_tasks if not t.done()]
                if in_flight:
                    get_logger(__name__).info(
                        "shutdown_in_flight_tasks", count=len(in_flight)
                    )

    app = FastAPI(title="audio-mcp", lifespan=lifespan)
    app.include_router(health_router.router)
    app.include_router(landing_router.router)
    app.include_router(upload_router.router)
    app.include_router(downloads_router.router)
    app.mount("/mcp", mcp_app)
    return app


app = create_app()
