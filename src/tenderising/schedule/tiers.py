"""T0-T4 collection runners (§7).

Each tier creates its own session/store, runs a crawl or a per-bid poll, records a
CollectionRun, and returns a summary. Fingerprint dedup makes re-crawls cheap no-ops.

The full GeM corpus spans four buyer-status facets, not just "ongoing" (§5,
revalidation §2): Ongoing, Technical Evaluated, Financial Evaluated, Bid/RA Awarded.
T3 keeps the active (ongoing) set converged; T4 enumerates the whole corpus.
"""

from __future__ import annotations

import time

from tenderising.collector.bids import BidCollector
from tenderising.collector.session import GemSession
from tenderising.config import BY_STATUS, FILTER_BY_STATUS, FILTER_ONGOING, POLITENESS, RunType
from tenderising.db.models import Bid, CollectionRun
from tenderising.db.models.base import utcnow
from tenderising.rag import index as rag_index
from tenderising.schedule.backoff import update_poll_state
from tenderising.schedule.score import PRE_AWARD, change_probability_score
from tenderising.service.store import CuratedStoreService

# Whole-corpus facets, biggest gap first so an interruptible backfill captures the
# largest missing set (awarded ~3.3M) before the already-covered ongoing set.
CORPUS_FACETS = [
    ("awarded", FILTER_BY_STATUS, BY_STATUS["awarded"]),
    ("financial-evaluated", FILTER_BY_STATUS, BY_STATUS["financial"]),
    ("tech-evaluated", FILTER_BY_STATUS, BY_STATUS["tech"]),
    ("ongoing", FILTER_ONGOING, None),
]


def _crawl(
    store: CuratedStoreService,
    collector: BidCollector,
    *,
    keyword: str,
    sort: str,
    status: str,
    by_status: str | None,
    max_pages: int | None,
    convergence_pages: int,
    min_pages: int,
    run_type: str,
    scope: str,
) -> dict:
    run = CollectionRun(type=run_type, scope=scope, start_ts=utcnow(), status="running")
    store.session.add(run)
    store.session.flush()

    seen = new = changed = 0
    quiet = 0
    pages_fetched = 0
    num_found = 0
    error = None
    start = time.monotonic()
    print(f"[{run_type} {scope}] starting crawl, max_pages={max_pages}", flush=True)

    page = 0
    while max_pages is None or page < max_pages:
        page += 1
        ok, nf, docs = collector.session.post_page_with_retry(
            keyword, page, sort=sort, status=status, by_status=by_status
        )
        if not ok:
            error = f"page {page} failed"
            break
        num_found = nf
        pages_fetched += 1
        page_delta = 0
        for doc in docs:
            bid_id, created, ch = collector.ingest_doc(doc)
            if bid_id is None:
                continue
            seen += 1
            if created:
                new += 1
                page_delta += 1
            if ch:
                changed += 1
                page_delta += 1
            update_poll_state(store, bid_id, changed=(created or ch))
        quiet = quiet + 1 if page_delta == 0 else 0
        if page % 10 == 0:
            store.commit()
        if page == 1 or page % 10 == 0:
            elapsed = time.monotonic() - start
            budget = f"/{max_pages}" if max_pages else ""
            print(
                f"[{run_type} {scope}] page {page}{budget} num_found={num_found} "
                f"seen={seen} new={new} changed={changed} elapsed={elapsed:.0f}s",
                flush=True,
            )
        if convergence_pages and quiet >= convergence_pages and page >= min_pages:
            break
        if nf and page * POLITENESS.page_size >= nf:
            break
        time.sleep(POLITENESS.request_delay_seconds)  # §7 politeness

    print(
        f"[{run_type} {scope}] finished pages={pages_fetched} num_found={num_found} "
        f"seen={seen} new={new} changed={changed} elapsed={time.monotonic() - start:.0f}s",
        flush=True,
    )

    run.end_ts = utcnow()
    if error and pages_fetched == 0:
        run.status = "failed"
    elif error:
        run.status = "partial"
    else:
        run.status = "completed"
    run.num_seen = seen
    run.num_new = new
    run.error_summary = error
    store.commit()

    return {
        "run_id": run.id,
        "pages_fetched": pages_fetched,
        "num_found": num_found,
        "num_seen": seen,
        "num_new": new,
        "num_changed": changed,
        "status": run.status,
        "error": error,
        "rag_reindex": _reindex_rag(),
    }


def _enumerate_corpus(
    store: CuratedStoreService,
    collector: BidCollector,
    *,
    sort: str,
    facets: list[tuple[str, str, str | None]],
    max_pages: int | None,
    run_type: str,
) -> dict:
    """Crawl multiple status facets in sequence (T4 whole-corpus enumeration).

    `max_pages` is a total page budget across facets (None = unbounded). One
    CollectionRun is recorded per facet so partial progress stays observable.
    """
    runs: list[dict] = []
    total_pages = total_seen = total_new = total_changed = 0
    budget = max_pages
    for label, status, by_status in facets:
        if budget is not None and budget <= 0:
            break
        r = _crawl(
            store,
            collector,
            keyword="",
            sort=sort,
            status=status,
            by_status=by_status,
            max_pages=budget,
            convergence_pages=0,
            min_pages=1,
            run_type=run_type,
            scope=f"corpus/{label}",
        )
        runs.append(r)
        total_pages += r["pages_fetched"]
        total_seen += r["num_seen"]
        total_new += r["num_new"]
        total_changed += r["num_changed"]
        if budget is not None:
            budget -= r["pages_fetched"]
    return {
        "facets": len(runs),
        "pages_fetched": total_pages,
        "num_seen": total_seen,
        "num_new": total_new,
        "num_changed": total_changed,
        "facet_runs": runs,
    }


def _reindex_rag() -> dict:
    """Rebuild the RAG index after a crawl. A failure must never fail the crawl."""
    try:
        return rag_index.refresh()
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _poll_bid_by_number(collector: BidCollector, bid_number: str) -> bool:
    """Re-poll one bid by its public number; ingest a matching doc if found."""
    ok, _nf, docs = collector.session.post_page_with_retry(
        bid_number, 1, sort="Bid-End-Date-Oldest"
    )
    if not ok:
        return False
    for doc in docs:
        num = doc.get("b_bid_number")
        num = num[0] if isinstance(num, list) and num else num
        if str(num) == bid_number:
            collector.ingest_doc(doc)
            return True
    return False


def _hot_bids(store: CuratedStoreService, top_n: int) -> list[Bid]:
    bids = store.session.query(Bid).filter(Bid.status_normalized.in_(PRE_AWARD)).all()
    return sorted(bids, key=change_probability_score, reverse=True)[:top_n]


def t0_on_demand(bid_number: str) -> dict:
    store = CuratedStoreService()
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    found = _poll_bid_by_number(collector, bid_number)
    store.commit()
    return {"bid_number": bid_number, "found": found}


def t1_hot_set(top_n: int = 50) -> dict:
    store = CuratedStoreService()
    hot = _hot_bids(store, top_n)
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    polled = 0
    for bid in hot:
        if _poll_bid_by_number(collector, bid.bid_number):
            polled += 1
    store.commit()
    return {"hot_candidates": len(hot), "polled": polled}


def t2_broad_delta(max_pages: int | None = None) -> dict:
    store = CuratedStoreService()
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    return _crawl(
        store,
        collector,
        keyword="",
        sort="Bid-End-Date-Newest",
        status=FILTER_ONGOING,
        by_status=None,
        max_pages=max_pages or POLITENESS.max_pages_delta,
        convergence_pages=POLITENESS.convergence_pages,
        min_pages=10,
        run_type=RunType.DELTA.value,
        scope="active-newest",
    )


def t3_baseline(max_pages: int | None = None) -> dict:
    store = CuratedStoreService()
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    return _crawl(
        store,
        collector,
        keyword="",
        sort="Bid-End-Date-Newest",
        status=FILTER_ONGOING,
        by_status=None,
        max_pages=max_pages or POLITENESS.max_pages_full,
        convergence_pages=0,
        min_pages=1,
        run_type=RunType.FULL.value,
        scope="ongoing-newest-full",
    )


def t4_weekly(max_pages: int | None = None) -> dict:
    """T4: weekly whole-corpus enumeration across all four status facets (§7).

    Unbounded by default (`max_pages=None`): pages each facet until `numFound` is
    exhausted. Pass `--max-pages` to bound the total page budget for a shorter run.
    """
    store = CuratedStoreService()
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    return _enumerate_corpus(
        store,
        collector,
        sort="Bid-End-Date-Newest",
        facets=CORPUS_FACETS,
        max_pages=max_pages,
        run_type=RunType.FULL.value,
    )


def t_award_delta(max_pages: int | None = None) -> dict:
    """Collect recently-awarded bids via the captcha-free 'Bid /RA Awarded' facet."""
    store = CuratedStoreService()
    collector = BidCollector(GemSession(), store)
    collector.session.refresh()
    return _crawl(
        store,
        collector,
        keyword="",
        sort="Bid-End-Date-Newest",
        status=FILTER_BY_STATUS,
        by_status=BY_STATUS["awarded"],
        max_pages=max_pages or POLITENESS.max_pages_delta,
        convergence_pages=POLITENESS.convergence_pages,
        min_pages=10,
        run_type=RunType.DELTA.value,
        scope="awarded-newest",
    )
