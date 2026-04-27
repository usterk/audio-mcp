"""`list_recent_jobs` MCP tool — overview with ETA fields."""
from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request
from mcp.types import ToolAnnotations

from app.tools._eta import status_payload_with_queue
from app.tools._schemas import JobInfo


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def list_recent_jobs(
        limit: int = 10, ctx: Context | None = None
    ) -> list[JobInfo]:
        """Return recently submitted jobs, newest first.

        Each entry includes the ETA-aware fields (``elapsed_sec``,
        ``eta_remaining_sec``, ``check_after_sec``, ``queue_position``,
        ``predicted_processing_sec``, ``processing_sec``) so agents can
        triage what's still in flight without calling ``get_job`` per
        UUID. Download URLs remain valid for as long as the artefacts
        exist on disk, even if the original session was interrupted.
        """
        request = get_http_request()
        state = request.app.state
        jobs_db = state.jobs_db
        queue = getattr(state, "job_queue", None)
        base_url = state.settings.public_base_url
        rows = await jobs_db.list_recent(limit=limit)
        out: list[JobInfo] = []
        for row in rows:
            payload = await status_payload_with_queue(
                job_row=row, queue=queue, base_url=base_url
            )
            out.append(JobInfo.model_validate(payload))
        return out
