"""Expose the package version in a single place."""
from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version

# Prefer the build-time version baked by the Aurora runner (--build-arg APP_VERSION,
# set as a runtime ENV in the Dockerfile); fall back to installed package metadata.
VERSION = os.getenv("APP_VERSION") or ""
if not VERSION:
    try:
        VERSION = version("audio-mcp")
    except PackageNotFoundError:  # pragma: no cover
        VERSION = "0.0.0"
