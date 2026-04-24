#!/usr/bin/env python3
"""Remove expired uploads. Usable standalone or from a cron."""
from __future__ import annotations

import asyncio

from app.config import get_settings
from app.storage.files import remove_expired_uploads
from app.storage.jobs_db import JobsDB


async def main() -> None:
    settings = get_settings()
    n_files = remove_expired_uploads(settings.data_dir, ttl_seconds=settings.upload_ttl_seconds)
    db = JobsDB(settings.data_dir / "jobs.db")
    await db.init()
    n_rows = await db.delete_expired_uploads()
    print(f"removed {n_files} files, {n_rows} rows")


if __name__ == "__main__":
    asyncio.run(main())
