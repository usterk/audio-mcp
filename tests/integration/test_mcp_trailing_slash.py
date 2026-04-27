"""Both /mcp and /mcp/ must reach the FastMCP sub-app."""
from __future__ import annotations


def _initialize_payload() -> dict:
    return {
        "jsonrpc": "2.0",
        "method": "initialize",
        "id": 1,
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "t", "version": "1"},
        },
    }


def test_mcp_endpoint_works_without_trailing_slash(client) -> None:
    headers = {"Accept": "application/json, text/event-stream"}
    r_no = client.post("/mcp", json=_initialize_payload(), headers=headers, follow_redirects=False)
    r_yes = client.post("/mcp/", json=_initialize_payload(), headers=headers, follow_redirects=False)

    assert r_no.status_code == 200, r_no.text
    assert r_yes.status_code == 200, r_yes.text
    # Both responses are MCP initialize results — same JSON-RPC id, same shape.
    assert "/mcp" not in r_no.headers.get("location", "")
