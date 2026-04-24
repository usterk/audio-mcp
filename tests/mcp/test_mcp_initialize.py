"""Smoke test: in-process MCP client discovers all tools + resource."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tools_and_resources_registered(client: TestClient) -> None:
    mcp = client.app.state.mcp
    tool_names = {t.name for t in await mcp.list_tools()}
    assert {
        "transcribe",
        "generate_audio",
        "list_voices",
        "list_recent_jobs",
        "usage_guide",
    } <= tool_names
    resources = await mcp.list_resources()
    assert any(str(r.uri) == "audio-mcp://docs/usage" for r in resources)
    instructions = mcp.instructions
    assert "transcribe" in instructions
    assert "generate_audio" in instructions
