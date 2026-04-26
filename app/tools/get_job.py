"""`get_job` MCP tool — single-uuid lookup with ETA fields."""
from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request

from app.tools._eta import status_payload_with_queue


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_job(uuid: str, ctx: Context | None = None) -> dict:
        """Look up a single job by UUID.

        Returns its current status, predicted/elapsed timing, ETA in
        seconds (for queued/running jobs), and download URLs. Agents
        should call this after a tool returned an async/queued payload,
        ideally after waiting ``check_after_sec`` seconds.
        """
        request = get_http_request()
        state = request.app.state
        jobs_db = state.jobs_db
        queue = getattr(state, "job_queue", None)
        base_url = state.settings.public_base_url
        row = await jobs_db.get_job(uuid)
        if row is None:
            raise ValueError(f"Unknown job UUID: {uuid}")
        return await status_payload_with_queue(
            job_row=row, queue=queue, base_url=base_url
        )
