"""GET /jobs/{uuid} and artefact downloads."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from app.storage.files import output_path

router = APIRouter()

_MIME_BY_EXT = {
    "json": ("application/json", "transcription"),
    "txt": ("text/plain; charset=utf-8", "transcription"),
    "mp3": ("audio/mpeg", "audio"),
    "wav": ("audio/wav", "audio"),
    "opus": ("audio/ogg", "audio"),
}


@router.get("/jobs/{uuid}")
async def job_metadata(request: Request, uuid: str) -> dict[str, Any]:
    row = await request.app.state.jobs_db.get_job(uuid)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return row


@router.get("/jobs/{uuid}/transcription.{ext}")
async def transcription_download(request: Request, uuid: str, ext: str) -> Any:
    if ext not in {"json", "txt"}:
        raise HTTPException(status_code=404, detail="unsupported transcription format")
    mime, kind = _MIME_BY_EXT[ext]
    path = output_path(request.app.state.settings.data_dir, uuid, kind, ext)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if ext == "json":
        return JSONResponse(json.loads(path.read_text()))
    return FileResponse(path, media_type=mime, filename=path.name)


@router.get("/jobs/{uuid}/audio.{ext}")
async def audio_download(request: Request, uuid: str, ext: str) -> Any:
    if ext not in {"mp3", "wav", "opus"}:
        raise HTTPException(status_code=404, detail="unsupported audio format")
    mime, kind = _MIME_BY_EXT[ext]
    path = output_path(request.app.state.settings.data_dir, uuid, kind, ext)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type=mime, filename=path.name)
