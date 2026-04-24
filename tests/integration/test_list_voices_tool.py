import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_voices_piper_includes_gosia(client: TestClient) -> None:
    result = await client.app.state.mcp.call_tool("list_voices", {"backend": "piper"})
    voices = result.structured_content["result"]
    ids = [v["id"] for v in voices]
    assert "gosia-medium" in ids


@pytest.mark.asyncio
async def test_unknown_backend_errors(client: TestClient) -> None:
    with pytest.raises((ValueError, Exception), match="does-not-exist|unknown"):  # noqa: B017
        await client.app.state.mcp.call_tool("list_voices", {"backend": "does-not-exist"})
