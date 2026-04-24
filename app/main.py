"""FastAPI app factory with FastMCP mounted at /mcp."""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

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
from app.storage.files import remove_expired_uploads
from app.storage.jobs_db import JobsDB


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
            app.state.jobs_db = JobsDB(settings.data_dir / "jobs.db")
            await app.state.jobs_db.init()
            app.state.semaphores = Semaphores(
                ConcurrencyLimits(
                    global_=settings.global_concurrency,
                    cpu=settings.cpu_backend_concurrency,
                )
            )
            app.state.active_jobs = 0
            app.state.backends_loaded = []

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

    app = FastAPI(title="audio-mcp", lifespan=lifespan)
    app.include_router(health_router.router)
    app.include_router(landing_router.router)
    app.include_router(upload_router.router)
    app.include_router(downloads_router.router)
    app.mount("/mcp", mcp_app)
    return app


app = create_app()
