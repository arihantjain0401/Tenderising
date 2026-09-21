"""MCP tool definitions over the service layer (search, detail, stats, live fetch, SQL, RAG)."""

from __future__ import annotations

from datetime import datetime

from tenderising.config import RAG_TOP_K, SQL_MAX_ROWS
from tenderising.mcp import sql as sql_mod
from tenderising.mcp.registry import ToolDefinition, ToolRegistry, fail, ok
from tenderising.rag import index as rag_index
from tenderising.rag import search as rag_search
from tenderising.service.fetch import LiveFetchService
from tenderising.service.skills import Skills
from tenderising.service.store import CuratedStoreService


def _parse_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _skills() -> Skills:
    return Skills(CuratedStoreService())


def _search_bids(params: dict) -> dict:
    try:
        s = _skills()
        return ok(
            s.search_bids(
                q=params.get("q"),
                status=params.get("status", "ongoing"),
                organization=params.get("organization"),
                department=params.get("department"),
                category=params.get("category"),
                end_after=_parse_dt(params.get("end_after")),
                end_before=_parse_dt(params.get("end_before")),
                limit=int(params.get("limit", 100)),
                offset=int(params.get("offset", 0)),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return fail(str(exc))


def _get_bid_detail(params: dict) -> dict:
    detail = _skills().get_bid_detail(b_id=params.get("b_id"), bid_number=params.get("bid_number"))
    if detail is None:
        return fail("bid not found")
    return ok(detail)


def _get_stats(params: dict) -> dict:  # noqa: ARG001
    return ok(_skills().get_stats())


def _get_changes(params: dict) -> dict:
    return ok(
        _skills().get_changes(
            since=_parse_dt(params.get("since")),
            kinds=params.get("kinds"),
            limit=int(params.get("limit", 200)),
        )
    )


def _live_fetch_bid(params: dict) -> dict:
    bid_number = params.get("bid_number")
    if not bid_number:
        return fail("bid_number is required")
    svc = LiveFetchService()
    try:
        bid = svc.fetch_bid(bid_number)
        if bid is None:
            return fail(f"no live bid found for {bid_number}")
        enrichment = svc.enrich(bid)
        detail = _skills().get_bid_detail(bid_number=bid_number)
        return ok({"bid_number": bid_number, "enrichment": enrichment, "detail": detail})
    except Exception as exc:  # noqa: BLE001
        return fail(str(exc))
    finally:
        svc.close()


def _run_sql(params: dict) -> dict:
    statement = params.get("sql", "").strip()
    if not statement:
        return fail("sql is required")
    result = sql_mod.run_sql(statement, max_rows=int(params.get("max_rows", SQL_MAX_ROWS)))
    if "error" in result:
        return fail(result["error"])
    return ok(result)


def _search_documents(params: dict) -> dict:
    query = params.get("query", "").strip()
    if not query:
        return fail("query is required")
    top_k = int(params.get("top_k", RAG_TOP_K))
    try:
        return ok(rag_search.search(query, top_k))
    except Exception as exc:  # noqa: BLE001 - e.g. embedding model not pulled yet
        return fail(f"RAG search failed (is the embedding model pulled?): {exc!r}")


def _refresh_rag_index(params: dict) -> dict:  # noqa: ARG001
    try:
        return ok(rag_index.refresh())
    except Exception as exc:  # noqa: BLE001
        return fail(f"index refresh failed: {exc!r}")


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolDefinition(
            name="search_bids",
            description=(
                "Search the curated bids table by keyword (matches bid number or item/category), "
                "status (ongoing|closed|all), buyer organization/department, category, and end-date "
                "range. Returns a count and a list of bids. Use for structured questions like "
                "'bids from Ministry of Defence', 'bids ending this week', 'bids for cement'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string"},
                    "status": {"type": "string", "enum": ["ongoing", "closed", "all"]},
                    "organization": {"type": "string"},
                    "department": {"type": "string"},
                    "category": {"type": "string"},
                    "end_after": {"type": "string", "description": "ISO date/datetime"},
                    "end_before": {"type": "string", "description": "ISO date/datetime"},
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                },
            },
            handler=_search_bids,
            tags=["read", "core"],
        )
    )
    reg.register(
        ToolDefinition(
            name="get_bid_detail",
            description=(
                "Full detail for one bid (buyer hierarchy, award, corrigenda, documents, line "
                "items, participation) given its public bid_number or internal b_id."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "bid_number": {"type": "string"},
                    "b_id": {"type": "string"},
                },
            },
            handler=_get_bid_detail,
            tags=["read", "core"],
        )
    )
    reg.register(
        ToolDefinition(
            name="get_stats",
            description="Summary counts of the curated DB (total/active bids, new/modified, recent runs).",
            input_schema={"type": "object", "properties": {}},
            handler=_get_stats,
            tags=["read", "core"],
        )
    )
    reg.register(
        ToolDefinition(
            name="get_changes",
            description="Recent changes (new/modified bids) since an ISO datetime.",
            input_schema={
                "type": "object",
                "properties": {
                    "since": {"type": "string", "description": "ISO datetime"},
                    "kinds": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer"},
                },
            },
            handler=_get_changes,
            tags=["read", "core"],
        )
    )
    reg.register(
        ToolDefinition(
            name="live_fetch_bid",
            description=(
                "On-demand live query of GeM for one bid by public number, then enrich it "
                "(documents, results, corrigenda) and return its detail. Hits the live GeM site."
            ),
            input_schema={
                "type": "object",
                "properties": {"bid_number": {"type": "string"}},
                "required": ["bid_number"],
            },
            handler=_live_fetch_bid,
            tags=["live", "gem"],
        )
    )
    reg.register(
        ToolDefinition(
            name="run_sql",
            description=(
                "Run a READ-ONLY SQL SELECT against the curated database to answer a flexible "
                "structured question. Tables/columns:\n" + sql_mod.schema_description()
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "sql": {"type": "string"},
                    "max_rows": {"type": "integer"},
                },
                "required": ["sql"],
            },
            handler=_run_sql,
            tags=["read", "sql"],
        )
    )
    reg.register(
        ToolDefinition(
            name="search_documents",
            description=(
                "Semantic (RAG) search over document text — BOQ/spec/GTC PDF extracts, corrigenda "
                "bodies, and line-item descriptions. Returns the most relevant chunks with source "
                "provenance. Use for free-text questions like 'what does the GTC say about delivery'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "required": ["query"],
            },
            handler=_search_documents,
            tags=["rag"],
        )
    )
    reg.register(
        ToolDefinition(
            name="refresh_rag_index",
            description="Rebuild the RAG vector index from the current document text.",
            input_schema={"type": "object", "properties": {}},
            handler=_refresh_rag_index,
            tags=["rag", "control"],
        )
    )
    return reg
