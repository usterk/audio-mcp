"""`list_recent_jobs` MCP tool — job-recovery safety net."""
from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def list_recent_jobs(limit: int = 10, ctx: Context | None = None) -> list[dict]:
        """Return recently submitted jobs, newest first.

        Use this to recover the result of a job whose MCP session was
        interrupted — the `download` URLs in each entry are always valid
        while the artefacts remain on disk.
        """
        request = get_http_request()
        app = request.app
        jobs = await app.state.jobs_db.list_recent(limit=limit)
        base = app.state.settings.public_base_url.rstrip("/")
        for j in jobs:
            uuid = j["uuid"]
            if j["kind"] == "transcribe":
                j["download"] = {
                    "json": f"{base}/jobs/{uuid}/transcription.json",
                    "txt": f"{base}/jobs/{uuid}/transcription.txt",
                }
            else:
                fmt = "mp3"
                j["download"] = {"audio": f"{base}/jobs/{uuid}/audio.{fmt}"}
        return jobs
