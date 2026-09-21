"""HTTP MCP surface: JSON responses for GET /tools and POST /call.

Mounted by the web app at /mcp/tools and /mcp/call; the same ToolRegistry is
shared with the chat agent, so both paths expose identical tools.
"""

from __future__ import annotations

import json

from tenderising.mcp.registry import ToolRegistry


def list_tools_json(registry: ToolRegistry) -> str:
    return json.dumps(registry.list_tools(), default=str)


def call_tool_json(registry: ToolRegistry, body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return json.dumps({"ok": False, "error": "invalid JSON body"})
    tool = payload.get("tool")
    params = payload.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    return json.dumps(registry.call(tool, params), default=str)
