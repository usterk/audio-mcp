"""Shared pytest fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Per-test data directory with uploads/ and outputs/ subdirs."""
    (tmp_path / "uploads").mkdir()
    (tmp_path / "outputs").mkdir()
    return tmp_path
