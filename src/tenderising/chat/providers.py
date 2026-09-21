"""Chat providers — local Ollama and cloud DeepSeek, both OpenAI-compatible.

One client class; the only differences are base URL, model, and auth. Ollama is
reached via its `/v1/chat/completions` OpenAI-compatible endpoint.
"""

from __future__ import annotations

import json
import urllib.request

from tenderising.config import (
    CHAT_MODEL,
    CHAT_PROVIDER,
    DEEPSEEK_API_URL,
    DEEPSEEK_MODEL,
    OLLAMA_BASE_URL,
    deepseek_api_key,
)

OLLAMA_COMPAT_URL = OLLAMA_BASE_URL + "/v1/chat/completions"


class ChatProvider:
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        msg = data["choices"][0]["message"]
        tool_calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            args = fn.get("arguments", "{}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tool_calls.append(
                {
                    "id": tc.get("id") or f"call_{i}",
                    "name": fn.get("name"),
                    "arguments": args if isinstance(args, dict) else {},
                }
            )
        return {"content": msg.get("content"), "tool_calls": tool_calls}

    def chat_stream(self, messages: list[dict], tools: list[dict]):
        """Stream a chat completion, yielding incremental events.

        Yields ``{"type": "thinking", "delta": str}`` for reasoning tokens,
        ``{"type": "content", "delta": str}`` for answer tokens, and a terminal
        ``{"type": "done", "content": str, "tool_calls": [...]}`` once the stream
        ends (tool-call fragments are buffered and assembled into the terminal
        event).

        Both Ollama's OpenAI-compatible endpoint and DeepSeek use the same
        ``data: {...}`` SSE framing; only the thinking-token field name differs
        (``reasoning_content`` vs ``thinking``), so both are read defensively.
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            self.base_url, data=json.dumps(payload).encode("utf-8"), headers=headers
        )

        content_parts: list[str] = []
        tool_parts: dict[int, dict] = {}  # index -> {id, name, arguments}

        with urllib.request.urlopen(req, timeout=300) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                for key in ("reasoning_content", "thinking", "reasoning"):
                    t = delta.get(key)
                    if t:
                        yield {"type": "thinking", "delta": t}
                        break

                c = delta.get("content")
                if c:
                    content_parts.append(c)
                    yield {"type": "content", "delta": c}

                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    entry = tool_parts.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        entry["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        entry["name"] += fn["name"]
                    if fn.get("arguments"):
                        entry["arguments"] += fn["arguments"]

        tool_calls = []
        for idx in sorted(tool_parts):
            entry = tool_parts[idx]
            args = entry["arguments"] or "{}"
            try:
                args_obj = json.loads(args)
            except json.JSONDecodeError:
                args_obj = {}
            tool_calls.append(
                {
                    "id": entry["id"] or f"call_{idx}",
                    "name": entry["name"] or None,
                    "arguments": args_obj if isinstance(args_obj, dict) else {},
                }
            )
        yield {"type": "done", "content": "".join(content_parts), "tool_calls": tool_calls}


def make_provider(provider: str | None = None, model: str | None = None) -> ChatProvider:
    provider = provider or CHAT_PROVIDER
    if provider == "deepseek":
        return ChatProvider(DEEPSEEK_API_URL, model or DEEPSEEK_MODEL, deepseek_api_key() or None)
    return ChatProvider(OLLAMA_COMPAT_URL, model or CHAT_MODEL)


def list_models() -> list[dict]:
    """Available chat models: DeepSeek (cloud, default) + tool-capable local models.

    DeepSeek is listed first so it is the default selection in the web dropdown.
    Only Ollama models that advertise tool-calling support (``capabilities``
    containing ``tools``) are offered: reasoning-only models such as
    ``deepseek-r1`` stream their chain-of-thought but never emit OpenAI-style
    ``tool_calls``, so the chat agent would fabricate answers instead of
    querying the database.
    """
    models: list[dict] = [{"provider": "deepseek", "model": DEEPSEEK_MODEL}]
    try:
        req = urllib.request.Request(OLLAMA_BASE_URL + "/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            caps = m.get("capabilities")
            if isinstance(caps, list):
                # Only tool-calling models can drive the agent loop; reasoning-
                # and completion-only models would hallucinate instead of querying.
                if "tools" not in caps:
                    continue
            elif "embed" in m["name"].lower():
                continue  # pre-capabilities Ollama: embedding models aren't chat models
            models.append({"provider": "ollama", "model": m["name"]})
    except Exception:  # noqa: BLE001 - Ollama unreachable -> still offer DeepSeek
        pass
    return models
