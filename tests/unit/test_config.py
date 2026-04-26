"""Unit tests for app.config."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


def test_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    s = Settings()
    assert s.data_dir == tmp_path
    assert s.upload_max_bytes == 500 * 1024 * 1024
    assert s.inline_base64_max_bytes == 10 * 1024 * 1024
    assert s.upload_ttl_seconds == 86_400
    assert s.global_concurrency == 5
    assert s.cpu_backend_concurrency == 1
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.public_base_url == ""  # derived at runtime if empty
    assert s.groq_api_key == ""
    assert s.openai_api_key == ""
    assert s.google_application_credentials == ""


def test_reads_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("AUDIO_MCP_PUBLIC_BASE_URL", "https://audio-mcp.test.ts.net")
    s = Settings()
    assert s.groq_api_key == "gsk_test"
    assert s.openai_api_key == "sk-test"
    assert s.public_base_url == "https://audio-mcp.test.ts.net"


def test_uploads_dir_created(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_path / "new"))
    s = Settings()
    s.ensure_dirs()
    assert (tmp_path / "new" / "uploads").is_dir()
    assert (tmp_path / "new" / "outputs").is_dir()
