"""POST /upload and GET /uploads/{upload_id}."""
from __future__ import annotations

import uuid as uuidlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from app.storage.files import upload_path, write_stream

router = APIRouter()


@router.post("/upload")
async def upload(request: Request, file: UploadFile) -> JSONResponse:
    settings = request.app.state.settings
    jobs_db = request.app.state.jobs_db
    upload_id = str(uuidlib.uuid4())
    content_type = file.content_type or "application/octet-stream"
    target = upload_path(settings.data_dir, upload_id, content_type)

    async def stream() -> Any:
        max_bytes = settings.upload_max_bytes
        written = 0
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                return
            written += len(chunk)
            if written > max_bytes:
                raise HTTPException(status_code=413, detail="upload exceeds configured size limit")
            yield chunk

    size = await write_stream(stream(), target)
    await jobs_db.create_upload(
        upload_id=upload_id,
        size_bytes=size,
        content_type=content_type,
        ttl_seconds=settings.upload_ttl_seconds,
    )
    return JSONResponse(
        {
            "upload_id": upload_id,
            "size_bytes": size,
            "content_type": content_type,
        }
    )


@router.get("/uploads/{upload_id}")
async def upload_metadata(request: Request, upload_id: str) -> dict[str, Any]:
    row = await request.app.state.jobs_db.get_upload(upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown upload")
    return row
