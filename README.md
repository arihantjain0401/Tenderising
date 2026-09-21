# tenderising — GeM procurement-intelligence platform

Implements `CLAUDE.md`: a **GeM-only**, public-data-only curated database, updated by the
T0–T4 collection schedules, with bid/result/document collectors and PDF extraction. The MCP
server and REST/HTTP surface are **out of scope** (CLAUDE.md §1); the service layer's read
"skills" are where a future MCP/HTTP wrapper would attach.

## Architecture

```
collector/  (fetch GeM, public, anonymous)  ──▶ service/  (CuratedStoreService + invariants)
                                                       └─▶ db/ (SQLAlchemy 2.0 + Alembic, SQLite WAL)
schedule/   (T0–T4 + awards)   extract/  (PDF integrity + BOQ/link extraction)
```

The database is reached only through the service layer. Raw evidence is written **before**
parsing (§6/§10); fingerprint changes append `change_events` (§4.9); missing/masked prices are
never zero (§4.6); raw status is kept separate from its derived label (§4.7).

## Setup (commands actually run and verified)

```bash
uv sync                              # install deps (SQLAlchemy, Alembic, PyMuPDF)
uv run alembic upgrade head          # build the schema into data/curated.db (SQLite WAL)
uv run pytest -q                     # 15 tests
uv run ruff check src                # lint (clean)
```

## Collection schedules

```bash
uv run tenderising on-demand GEM/2026/B/7904762   # T0 — fetch one bid by number
uv run tenderising hot-set --top 50               # T1 — re-poll top-N change-likely bids
uv run tenderising delta --max-pages 400          # T2 — broad active delta (convergence crawl)
uv run tenderising baseline --max-pages 6000      # T3 — nightly full convergence crawl
uv run tenderising weekly --max-pages 6000        # T4 — weekly full enumeration
uv run tenderising awards --max-pages 400         # collect recently-awarded bids (Awarded facet)
```

## Revalidation (CLAUDE.md §3)

Live findings are recorded in `docs/revalidation-2026-09-19.md`. Summary of what is reachable
headlessly (no login, no captcha bypass):

- **Bids** — `searchBid` listing (ongoing + status facets).
- **Awards + participation** — `Bid /RA Awarded` facet + `getBidResultView/<b_id>` (technical +
  financial tables, L1 rank, prices).
- **Documents/PDFs** — `showbidDocument/<b_id>` (valid bid-document PDF); every document it links
  (BOQ CSV/PDF, specs, GTC, OMP, shared docs) is fetched and indexed as a first-class `bid_document`.
- **Corrigenda** — `viewCorrigendum/<b_id>` + `getPublicTchtml/<iid>` (list + body text), CSRF-only.
- **BOQ line items** — the `BoqLineItemsDocument` CSV linked inside the bid-document PDF, parsed
  into `bid_line_items`.

Blocked / unverified: `contracts` and `direct_orders` (captcha-gated `view_contracts`, §3 — no
bypass); per-item specs via `showSpecs` (needs item-level IDs absent from the listing — BOQ content
is read from the linked CSV instead).

## Enrichment (on-demand)

`LiveFetchService.enrich(bid)` collects the bid's document, evaluation results (participation +
award), and corrigenda in one pass:

```bash
uv run python -c "from tenderising.service.fetch import LiveFetchService; \
from tenderising.db.models import Bid; \
svc=LiveFetchService(); \
b=svc.store.session.query(Bid).filter(Bid.bid_number=='GEM/2026/B/7131093').first(); \
print(svc.enrich(b))"
```

## Web index (read-only)

A minimal "index of bids" site (stdlib `http.server`, port 8070):

- `/` — paginated index of bids (bid number, item/category, buyer, end date, status, qty).
- `/bid/<bid_number>` — one bid's detail (buyer, award, corrigenda, documents, line items, participation).
- `/stats` — DB summary. `/health` — liveness.

```bash
uv run python -m tenderising.web.app     # serve on :8070
```

## launchd jobs (installed)

| Label | Schedule | Runs |
|---|---|---|
| `com.tenderising.baseline` | daily 03:15 IST | `tenderising baseline` (T3 full convergence) |
| `com.tenderising.delta` | 09:15 / 13:15 / 16:15 IST | `tenderising delta` (T2 broad active delta) |
| `com.tenderising.web` | KeepAlive | the web index above |
| `com.tenderising.ngrok` | KeepAlive | `ngrok start gemsite` → public URL (see `curl http://127.0.0.1:4040/api/tunnels`) |

Plists live in `deploy/launchd/` and are installed to `~/Library/LaunchAgents/`.

## Chat assistant + MCP (hybrid SQL + RAG)

An LLM chatbot at `/chatlocal` on the same site, backed by a local model with **tool-calling**.

- `GET /chatlocal` — chat UI. `POST /chatlocal/api/chat` (`{"message": …}`) → `{answer, tool_rounds}`.
- `GET /mcp/tools`, `POST /mcp/call` — the MCP tool surface (same registry the chat uses).

Tools: `search_bids`, `get_bid_detail`, `get_stats`, `get_changes`, `live_fetch_bid` (on-demand
GeM), `run_sql` (read-only SELECT), `search_documents` (RAG), `refresh_rag_index`.

Model providers (config in `tenderising/config.py`):

- `CHAT_PROVIDER="ollama"` + `CHAT_MODEL="qwen3:8b"` (local, default) — or `llama3.1:8b`,
  `qwen2.5-coder:14b`.
- `CHAT_PROVIDER="deepseek"` + `DEEPSEEK_API_KEY` env var (cloud `deepseek-chat`).

RAG uses the `nomic-embed-text` embedding model (pulled once via
`OLLAMA_HOST=http://127.0.0.1:11435 ollama pull nomic-embed-text`) and a rebuildable index at
`data/rag_index.sqlite` (refresh with the `refresh_rag_index` tool or `uv run python -c
"from tenderising.rag.index import refresh; print(refresh())"`).

