"""`usage_guide` tool — returns the bundled markdown guide."""
from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP


def _guide_text() -> str:
    candidate_paths = [
        Path("/app/docs/usage.md"),
        Path(__file__).resolve().parents[2] / "docs" / "usage.md",
    ]
    for p in candidate_paths:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return "usage guide not bundled in this image"


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def usage_guide() -> str:
        """Return the agent-facing markdown usage guide (workflows + examples)."""
        return _guide_text()
