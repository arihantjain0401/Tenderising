from tenderising.mcp.registry import ToolRegistry, fail, ok
from tenderising.mcp.sql import is_read_only, schema_description
from tenderising.mcp.tools import build_registry
from tenderising.rag.index import chunk_text
from tenderising.rag.search import _cosine


def test_is_read_only():
    assert is_read_only("SELECT * FROM bids")
    assert is_read_only("select count(*) from bids limit 5")
    assert is_read_only("WITH x AS (SELECT 1) SELECT * FROM x")
    assert is_read_only("PRAGMA table_info(bids)")
    assert not is_read_only("INSERT INTO bids VALUES (1)")
    assert not is_read_only("UPDATE bids SET x=1")
    assert not is_read_only("DROP TABLE bids")
    assert not is_read_only("DELETE FROM bids")
    assert not is_read_only("SELECT * FROM bids; DROP TABLE bids")


def test_schema_description():
    desc = schema_description()
    assert "bids(" in desc
    assert "awards(" in desc
    assert "buyer_orgs(" in desc


def test_registry_tools():
    reg = build_registry()
    names = set(reg.names())
    for expected in [
        "search_bids",
        "get_bid_detail",
        "get_stats",
        "get_changes",
        "live_fetch_bid",
        "run_sql",
        "search_documents",
        "refresh_rag_index",
    ]:
        assert expected in names
    tools = reg.to_openai_tools()
    assert all(t["type"] == "function" and "function" in t for t in tools)


def test_registry_unknown_tool():
    reg = ToolRegistry()
    assert reg.call("nope", {}) == fail("unknown tool: nope")
    assert ok(1) == {"ok": True, "data": 1}


def test_chunk_text():
    assert chunk_text("short") == ["short"]
    assert chunk_text("") == []
    text = "x" * 3000
    chunks = chunk_text(text, size=1500, overlap=200)
    assert len(chunks) >= 2
    assert all(len(c) <= 1500 for c in chunks)


def test_cosine():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine([], [1.0]) == 0.0
