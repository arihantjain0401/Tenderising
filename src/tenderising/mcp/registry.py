"""Tool registry: definitions + handlers, shared by the chat agent and the HTTP MCP endpoint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def ok(data: Any = None) -> dict:
    return {"ok": True, **({"data": data} if data is not None else {})}


def fail(error: str) -> dict:
    return {"ok": False, "error": str(error)}


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], dict]
    tags: list[str] = field(default_factory=list)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def names(self) -> list[str]:
        return list(self._tools)

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "tags": t.tags,
            }
            for t in self._tools.values()
        ]

    def to_openai_tools(self) -> list[dict]:
        """OpenAI/Ollama `tools` shape for function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self._tools.values()
        ]

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def call(self, name: str, params: dict | None = None) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            return fail(f"unknown tool: {name}")
        try:
            return tool.handler(params or {})
        except Exception as exc:  # noqa: BLE001 - handlers must never raise into the LLM
            return fail(f"{name} failed: {exc!r}")
