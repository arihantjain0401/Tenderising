"""CollagePlanner: deterministic tool-result -> widget mapping.

Reuses the agent's structured tool-call arguments as the intent signal and fires
complementary read queries so the collage is complete regardless of which tools
the local model happened to call. Raw tool results are never emitted; every
widget is sanitized through ``schemas``.
"""

from __future__ import annotations

from datetime import datetime

from tenderising.api import schemas
from tenderising.service.skills import Skills
from tenderising.service.store import CuratedStoreService

SEARCH_FILTER_KEYS = (
    "q",
    "status",
    "ministry",
    "department",
    "organization",
    "category",
    "bid_type",
    "is_high_value",
    "has_boq",
    "has_documents",
    "published_after",
    "published_before",
    "end_after",
    "end_before",
)


def _unwrap(result) -> dict | None:
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    data = result.get("data")
    return data if isinstance(data, dict) else None


def _dt(value):
    if isinstance(value, datetime) or value is None:
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _search_filters(arguments: dict) -> dict:
    out: dict = {}
    for key in SEARCH_FILTER_KEYS:
        value = arguments.get(key)
        if value in (None, ""):
            continue
        if key.endswith("_after") or key.endswith("_before"):
            value = _dt(value)
            if value is None:
                continue
        out[key] = value
    return out


def _interpret_summary(message: str, filters: dict) -> str:
    """One-line "Interpreted as" from the query plus the filters actually applied."""
    parts = []
    if filters.get("category"):
        parts.append(f"in {filters['category']}")
    if filters.get("status"):
        parts.append(f"status {filters['status']}")
    if filters.get("is_high_value"):
        parts.append("high value")
    if filters.get("has_boq"):
        parts.append("with BOQ")
    suffix = " · ".join(parts)
    return f"Interpreted as: “{message}”" + (f" — {suffix}" if suffix else "")


def _refinement_chips(message: str, filters: dict) -> list[dict]:
    """Quick chips to tighten the query; each carries a re-phrased prompt to re-ask."""
    chips: list[dict] = []

    def add(label: str, phrase: str) -> None:
        chips.append({"label": label, "prompt": f"{message}, {phrase}"})

    if "status" not in filters:
        add("Closing soon", "closing soon")
        add("Awarded", "awarded")
    if not filters.get("is_high_value"):
        add("High value only", "high value only")
    if not filters.get("has_boq"):
        add("With BOQ", "with BOQ")
    return chips[:4]


def interpret_query(message: str, arguments: dict) -> dict:
    """Deterministic interpretation of a query for the Ask UI (summary + chips)."""
    filters = _search_filters(arguments or {})
    return {
        "summary": _interpret_summary(message, filters),
        "chips": _refinement_chips(message, filters),
    }


def plan_widgets(name: str, arguments: dict, result) -> list[dict]:
    """Return sanitized widget descriptors for one executed tool round."""
    widgets: list[dict] = []

    if name == "search_bids":
        data = _unwrap(result)
        bids = (data or {}).get("bids", [])
        total = (data or {}).get("count", len(bids))
        filters = _search_filters(arguments or {})
        widgets.append(
            {
                "id": "result_table",
                "kind": "bid_table",
                "title": f"{total} matching bids",
                "data": {
                    "total": total,
                    "bids": [schemas.public_bid(b) for b in bids[:20]],
                    "filters": filters,
                },
            }
        )
        store = CuratedStoreService()
        try:
            skills = Skills(store)
            insights = skills.scoped_insights(**filters)
            widgets.append(
                {
                    "id": "summary_cards",
                    "kind": "summary_cards",
                    "title": "At a glance",
                    "data": insights,
                }
            )
            deadlines = skills.deadline_histogram(**filters)
            if sum(b["count"] for b in deadlines) > 0:
                widgets.append(
                    {
                        "id": "deadline_chart",
                        "kind": "deadline_chart",
                        "title": "Deadlines",
                        "data": {"buckets": deadlines},
                    }
                )
            departments = skills.top_departments(**filters)
            if departments:
                widgets.append(
                    {
                        "id": "buyer_breakdown",
                        "kind": "buyer_breakdown",
                        "title": "Top buyers",
                        "data": {"departments": departments},
                    }
                )
        except Exception:  # noqa: BLE001 - a scoped aggregate failure must not break the answer
            pass
        finally:
            store.close()

    elif name == "get_bid_detail":
        detail = _unwrap(result)
        if detail:
            widgets.append(
                {
                    "id": "bid_preview",
                    "kind": "bid_preview",
                    "title": "Bid preview",
                    "data": schemas.public_bid_detail(detail),
                }
            )

    elif name == "get_stats":
        stats = _unwrap(result)
        if stats:
            widgets.append(
                {
                    "id": "summary_cards",
                    "kind": "summary_cards",
                    "title": "Database",
                    "data": stats,
                }
            )

    return widgets
