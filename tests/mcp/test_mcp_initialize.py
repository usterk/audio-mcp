"""Smoke test: in-process MCP client discovers all tools and instructions."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tools_and_instructions_registered(client: TestClient) -> None:
    mcp = client.app.state.mcp
    tool_names = {t.name for t in await mcp.list_tools()}
    assert {
        "transcribe",
        "generate_audio",
        "list_voices",
        "list_recent_jobs",
        "get_job",
    } <= tool_names
    # The usage-guide tool/resource has been retired; long-audio guidance
    # lives in the server-level instructions and tool descriptions instead.
    assert "usage_guide" not in tool_names
    instructions = mcp.instructions
    assert "transcribe" in instructions
    assert "generate_audio" in instructions
    assert "mode='fast'|'offline'" in instructions
