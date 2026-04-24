"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Per-test data directory with uploads/ and outputs/ subdirs."""
    (tmp_path / "uploads").mkdir()
    (tmp_path / "outputs").mkdir()
    return tmp_path


@pytest.fixture
def client(tmp_data_dir, monkeypatch):
    monkeypatch.setenv("AUDIO_MCP_DATA_DIR", str(tmp_data_dir))
    app = create_app()
    with TestClient(app) as c:
        yield c
