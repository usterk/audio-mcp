"""SQLite-backed job and upload store."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    uuid        TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    backend     TEXT NOT NULL,
    status      TEXT NOT NULL,
    params_json TEXT NOT NULL,
    result_json TEXT,
    error       TEXT,
    created_at  INTEGER NOT NULL,
    finished_at INTEGER
);
CREATE INDEX IF NOT EXISTS jobs_created_at ON jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS uploads (
    upload_id    TEXT PRIMARY KEY,
    size_bytes   INTEGER NOT NULL,
    content_type TEXT,
    created_at   INTEGER NOT NULL,
    expires_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS uploads_expires_at ON uploads (expires_at);
"""


class JobsDB:
    def __init__(self, path: Path) -> None:
        self._path = path

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()

    async def create_job(
        self,
        *,
        uuid: str,
        kind: str,
        backend: str,
        params: dict[str, Any],
    ) -> None:
        now = int(time.time())
        async with aiosqlite.connect(self._path) as conn:
            await conn.execute(
                "INSERT INTO jobs (uuid, kind, backend, status, params_json, created_at) "
                "VALUES (?, ?, ?, 'running', ?, ?)",
                (uuid, kind, backend, json.dumps(params), now),
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
