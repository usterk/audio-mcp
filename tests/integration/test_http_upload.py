"""Upload endpoint tests."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient


def test_upload_returns_uuid_and_persists(client: TestClient, tmp_data_dir: Path) -> None:
    r = client.post(
        "/upload",
        files={"file": ("hi.wav", io.BytesIO(b"RIFFxxxxWAVE"), "audio/wav")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "upload_id" in data
    assert data["size_bytes"] == len(b"RIFFxxxxWAVE")
    assert data["content_type"] == "audio/wav"
    stored = list((tmp_data_dir / "uploads").glob("*.wav"))
    assert len(stored) == 1
    assert stored[0].stem == data["upload_id"]


def test_upload_metadata_endpoint(client: TestClient) -> None:
    r = client.post(
        "/upload",
        files={"file": ("a.mp3", io.BytesIO(b"\xff\xfbxxxx"), "audio/mpeg")},
    )
    uid = r.json()["upload_id"]
    m = client.get(f"/uploads/{uid}")
    assert m.status_code == 200
    assert m.json()["upload_id"] == uid


def test_upload_oversize_returns_413(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AUDIO_MCP_UPLOAD_MAX_BYTES", "4")
    # Rebuild the client to pick up new env.
    from fastapi.testclient import TestClient as TC  # noqa: N817, PLC0415

    from app.main import create_app  # noqa: PLC0415

    app = create_app()
    with TC(app) as c:
        r = c.post("/upload", files={"file": ("a.mp3", io.BytesIO(b"xxxxxxxx"), "audio/mpeg")})
    assert r.status_code == 413


def test_missing_upload_is_404(client: TestClient) -> None:
    r = client.get("/uploads/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
