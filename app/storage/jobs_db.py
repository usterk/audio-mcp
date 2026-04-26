"""SQLite-backed job and upload store."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

_TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uuid                     TEXT PRIMARY KEY,
    kind                     TEXT NOT NULL,
    backend                  TEXT NOT NULL,
    status                   TEXT NOT NULL,
    params_json              TEXT NOT NULL,
    result_json              TEXT,
    error                    TEXT,
    created_at               INTEGER NOT NULL,
    started_at               INTEGER,
    finished_at              INTEGER,
    size_proxy               REAL,
    predicted_processing_sec REAL,
    model_key                TEXT
);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id    TEXT PRIMARY KEY,
    size_bytes   INTEGER NOT NULL,
    content_type TEXT,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL
);
"""

_INDEXES_SCHEMA = """
CREATE INDEX IF NOT EXISTS jobs_created_at ON jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS jobs_stats_lookup ON jobs (kind, backend, model_key, status);
CREATE INDEX IF NOT EXISTS uploads_expires_at ON uploads (expires_at);
"""

_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("started_at", "ALTER TABLE jobs ADD COLUMN started_at INTEGER"),
    ("size_proxy", "ALTER TABLE jobs ADD COLUMN size_proxy REAL"),
    ("predicted_processing_sec", "ALTER TABLE jobs ADD COLUMN predicted_processing_sec REAL"),
    ("model_key", "ALTER TABLE jobs ADD COLUMN model_key TEXT"),
)


class JobsDB:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.executescript(_TABLES_SCHEMA)
            async with conn.execute("PRAGMA table_info(jobs)") as cur:
                existing = {row[1] for row in await cur.fetchall()}
            for col, ddl in _MIGRATIONS:
                if col not in existing:
                    await conn.execute(ddl)
            await conn.executescript(_INDEXES_SCHEMA)
            await conn.commit()

    async def create_job(
        self,
        *,
        uuid: str,
        kind: str,
        backend: str,
        params: dict[str, Any],
        status: str = "queued",
        size_proxy: float | None = None,
        predicted_processing_sec: float | None = None,
        model_key: str | None = None,
    ) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO jobs (uuid, kind, backend, status, params_json, created_at, "
                "size_proxy, predicted_processing_sec, model_key) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid,
                    kind,
                    backend,
                    status,
                    json.dumps(params),
                    now,
                    size_proxy,
                    predicted_processing_sec,
                    model_key,
                ),
            )
            await conn.commit()

    async def mark_started(self, uuid: str) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE jobs SET status='running', started_at=? WHERE uuid=?",
                (now, uuid),
            )
            await conn.commit()

    async def update_size_proxy(
        self,
        uuid: str,
        *,
        size_proxy: float,
        predicted_processing_sec: float | None = None,
    ) -> None:
        async with aiosqlite.connect(self._path) as conn:
            if predicted_processing_sec is None:
                await conn.execute(
                    "UPDATE jobs SET size_proxy=? WHERE uuid=?",
                    (size_proxy, uuid),
                )
            else:
                await conn.execute(
                    "UPDATE jobs SET size_proxy=?, predicted_processing_sec=? WHERE uuid=?",
                    (size_proxy, predicted_processing_sec, uuid),
                )
            await conn.commit()

    async def mark_done(self, uuid: str, *, result: dict[str, Any]) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE jobs SET status='done', result_json=?, finished_at=? WHERE uuid=?",
                (json.dumps(result), now, uuid),
            )
            await conn.commit()

    async def mark_failed(self, uuid: str, *, error: str) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=? WHERE uuid=?",
                (error, now, uuid),
            )
            await conn.commit()

    async def get_job(self, uuid: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM jobs WHERE uuid=?", (uuid,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def list_recent(self, *, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def list_unfinished(self) -> list[dict[str, Any]]:
        """Return queued/running rows. Used by restart sweep to mark them failed."""
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM jobs WHERE status IN ('queued', 'running')"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def query_recent_done(
        self,
        *,
        kind: str,
        backend: str,
        model_key: str | None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return recent successful jobs for stats. Only rows with size_proxy and started_at set."""
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT size_proxy, started_at, finished_at FROM jobs "
                "WHERE kind=? AND backend=? AND model_key IS ? AND status='done' "
                "AND size_proxy IS NOT NULL AND started_at IS NOT NULL "
                "AND finished_at IS NOT NULL "
                "ORDER BY finished_at DESC LIMIT ?",
                (kind, backend, model_key, limit),
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def create_upload(
        self,
        *,
        upload_id: str,
        size_bytes: int,
        content_type: str,
        ttl_seconds: int,
    ) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO uploads (upload_id, size_bytes, content_type, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (upload_id, size_bytes, content_type, now, now + ttl_seconds),
            )
            await conn.commit()

    async def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM uploads WHERE upload_id=?", (upload_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def delete_expired_uploads(self, *, now: float | None = None) -> int:
        t = int(now if now is not None else time.time())
        async with aiosqlite.connect(self._path) as conn, conn.execute(
            "DELETE FROM uploads WHERE expires_at < ?", (t,)
        ) as cur:
            await conn.commit()
            return cur.rowcount or 0
