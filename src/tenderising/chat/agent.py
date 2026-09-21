"""Tool-calling agent loop: question -> provider (tools) -> tool results -> answer."""

from __future__ import annotations

import json

from tenderising.chat.providers import make_provider
from tenderising.mcp.registry import ToolRegistry

SYSTEM_PROMPT = (
    "You are a GeM (Government e-Marketplace) procurement-data assistant with direct access to a "
    "local database of bids, reverse auctions, awards, contracts, sellers and buyers through the "
    "tools provided to you. "
    "ALWAYS use the tools to answer: you have live access to the data through them, so never say "
    "you cannot search, browse or access the data. Before answering any question about the data, "
    "call the appropriate tool and base your answer on its results; never invent numbers or "
    "speculate when a tool can give the real answer. "
    "For counts, filters, lists and aggregates use search_bids, run_sql, or get_stats. "
    "For free-text questions about documents/terms use search_documents. "
    "For one specific bid use get_bid_detail (or live_fetch_bid to query the live GeM site). "
    "Answer concisely and state what data you found."
)

# Cap prior turns fed back to the model so long conversations don't blow the context window.
MAX_HISTORY = 20


def _base_messages(question: str, history: list[dict] | None) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in (history or [])[-MAX_HISTORY:]:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})
    return messages


def answer_stream(
    question: str,
    registry: ToolRegistry,
    history: list[dict] | None = None,
    max_rounds: int = 6,
    provider=None,
):
    """Tool-calling agent loop as a generator of streaming events.

    Yields:
      ``{"type": "thinking", "delta": str}``   — model reasoning tokens,
      ``{"type": "answer", "delta": str}``     — answer tokens (streamed live),
      ``{"type": "tool", "name", "arguments", "result"}`` — a tool was executed,
      ``{"type": "done", "answer", "tool_rounds"}``        — terminal event.

    Intermediate round content (e.g. "I'll search for that…") is streamed as
    ``answer`` deltas for transparency, but only the *final* round's content is
    reported as ``answer`` on ``done`` (matching the non-streaming contract).
    """
    provider = provider or make_provider()
    tools = registry.to_openai_tools()
    messages = _base_messages(question, history)
    rounds: list[dict] = []
    last_content = ""

    for _ in range(max_rounds):
        done = None
        for ev in provider.chat_stream(messages, tools):
            if ev["type"] == "thinking":
                yield {"type": "thinking", "delta": ev["delta"]}
            elif ev["type"] == "content":
                yield {"type": "answer", "delta": ev["delta"]}
            elif ev["type"] == "done":
                done = ev
        if done is None:
            break
        if done.get("content"):
            last_content = done["content"]
        if not done.get("tool_calls"):
            yield {"type": "done", "answer": last_content, "tool_rounds": rounds}
            return

        assistant = {
            "role": "assistant",
            "content": done.get("content"),
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in done["tool_calls"]
            ],
        }
        messages.append(assistant)
        for tc in done["tool_calls"]:
            result = registry.call(tc["name"], tc["arguments"])
            rounds.append({"tool": tc["name"], "arguments": tc["arguments"], "result": result})
            yield {
                "type": "tool",
                "name": tc["name"],
                "arguments": tc["arguments"],
                "result": result,
            }
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, default=str),
                }
            )

    yield {
        "type": "done",
        "answer": last_content,
        "tool_rounds": rounds,
        "note": "max tool rounds reached",
    }


def answer(
    question: str,
    registry: ToolRegistry,
    history: list[dict] | None = None,
    max_rounds: int = 6,
    provider=None,
) -> dict:
    """Non-streaming wrapper over :func:`answer_stream`, keeping the original contract."""
    result: dict = {"answer": "", "tool_rounds": []}
    for ev in answer_stream(
        question, registry, history=history, max_rounds=max_rounds, provider=provider
    ):
        if ev["type"] == "done":
            result["answer"] = ev.get("answer", "")
            result["tool_rounds"] = ev.get("tool_rounds", [])
            if "note" in ev:
                result["note"] = ev["note"]
    return result


def suggest_followups(
    question: str,
    history: list[dict] | None = None,
    answer: str | None = None,
    provider=None,
) -> list[str]:
    """Generate 3 short, conversation-relevant follow-up questions.

    Uses the same provider/model as the answer (``make_provider``) so the hints
    reflect "whatever model is driving the session". Best-effort: returns at most
    3 strings, empty list on failure.
    """
    provider = provider or make_provider()
    convo = "\n".join(
        f"{m.get('role')}: {m.get('content')}" for m in (history or [])[-8:]
    )
    prompt = (
        "Based on this procurement-intelligence conversation, suggest exactly 3 short, "
        "distinct follow-up questions the user is most likely to ask next. Reply with ONLY "
        "a JSON array of 3 strings, no other text.\n\n"
        f"Question: {question}\n\nConversation:\n{convo}\n\nFinal answer:\n{answer or ''}"
    )
    messages = [
        {"role": "system", "content": "You reply with valid JSON only."},
        {"role": "user", "content": prompt},
    ]
    try:
        result = provider.chat(messages, tools=[])
        return _parse_hints(result.get("content") or "")[:3]
    except Exception:  # noqa: BLE001 - hints are best-effort, never fail the turn
        return []


def _parse_hints(content: str) -> list[str]:
    """Extract up to 3 follow-up strings from an LLM reply (robust to prose/fences)."""
    text = (content or "").strip()

    def _clean(items: list) -> list[str]:
        return [str(x).strip() for x in items if str(x).strip()][:3]

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return _clean(data)
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    return _clean(value)
    except json.JSONDecodeError:
        pass

    # Fall back to the first JSON array found anywhere in the reply.
    start = text.find("[")
    while start != -1:
        end = text.find("]", start)
        if end == -1:
            break
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, list):
                return _clean(data)
        except json.JSONDecodeError:
            pass
        start = text.find("[", start + 1)

    # Final fallback: split non-empty lines, strip list markers.
    return [ln.strip(" -*•0123456789.)").strip() for ln in text.splitlines() if ln.strip()][:3]
