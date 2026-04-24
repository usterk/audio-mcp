"""Expose the package version in a single place."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    VERSION = version("audio-mcp")
except PackageNotFoundError:  # pragma: no cover
    VERSION = "0.0.0"
