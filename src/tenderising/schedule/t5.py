"""T5 — fast, temporary parallel corpus snapshot.

High-concurrency raw fetch of the non-ongoing GeM facets (awarded / financial /
tech-evaluated). No dedup, no curated-DB writes: each worker writes raw searchBid
pages to its own JSONL under data/t5/raw/. A later merge step analyses duplicates
and missing pages before anything reaches the curated DB.

Resumable: pages already present in any data/t5/**/*.jsonl are skipped, and the
remaining work is distributed across the workers, so a stopped run can be restarted
(optionally with different worker count/period) without re-fetching.

Politeness: per-worker `period` between requests, phase-offset by `stagger`; 403/
429/5xx trigger backoff rather than hammering. The global scrape.lock is NOT taken.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import time
from datetime import UTC, datetime

from tenderising.collector.session import GemSession
from tenderising.config import BY_STATUS, DATA_DIR, FILTER_BY_STATUS, POLITENESS

T5_DIR = DATA_DIR / "t5"
RAW_DIR = T5_DIR / "raw"
PROGRESS_DIR = T5_DIR / "progress"
STOP_FILE = T5_DIR / "stop"
PROXY_LIST_FILE = T5_DIR / "proxies.txt"
PROXY_ENV = "T5_PROXIES"

# Non-ongoing facets only — ongoing_bids (~45k) is already largely collected.
FACETS = [
    ("awarded", FILTER_BY_STATUS, BY_STATUS["awarded"]),
    ("financial-evaluated", FILTER_BY_STATUS, BY_STATUS["financial"]),
    ("tech-evaluated", FILTER_BY_STATUS, BY_STATUS["tech"]),
]

SORT = "Bid-End-Date-Newest"
DEFAULT_PERIOD = 0.2
DEFAULT_STAGGER = 0.2
BACKOFF_BASE = 15.0
BACKOFF_MAX = 120.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


def load_proxies() -> list[str]:
    """Per-worker egress proxies (testing). One per line, or comma/env-separated.

    Read from $T5_PROXIES first, else data/t5/proxies.txt. Blank lines and '#'
    comments are skipped. An empty list means direct egress (no proxy).
    """
    raw = os.environ.get(PROXY_ENV, "").strip()
    if raw:
        return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
    if not PROXY_LIST_FILE.exists():
        return []
    out: list[str] = []
    for line in PROXY_LIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _mask_proxy(proxy: str | None) -> str | None:
    """Proxy host:port with any user:pass stripped, for safe display/logging."""
    if not proxy:
        return None
    rest = proxy.split("://", 1)[1] if "://" in proxy else proxy
    if "@" in rest:
        rest = rest.split("@", 1)[1]
    return rest


def _egress_ip() -> str | None:
    """Best-effort read of the effective egress IP via the current proxy env.

    Hits a neutral echo (api.ipify.org), never GeM. Returns None on any failure.
    """
    import urllib.request

    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=4) as r:
            return r.read().decode("ascii", errors="replace").strip()
    except Exception:
        return None


def fetch_facets() -> list[dict]:
    """Return facet descriptors with live numFound and global page offsets."""
    session = GemSession()
    session.refresh()
    facets: list[dict] = []
    offset = 0
    for label, status, by_status in FACETS:
        ok, nf, _ = session.post_page_with_retry(
            "", 1, sort=SORT, status=status, by_status=by_status
        )
        pages = math.ceil(nf / POLITENESS.page_size) if ok and nf else 0
        facets.append(
            {
                "label": label,
                "status": status,
                "by_status": by_status,
                "num_found": nf if ok else 0,
                "pages": pages,
                "start": offset,
            }
        )
        offset += pages
    return facets


def resolve_page(facets: list[dict], global_page: int):
    for f in facets:
        if f["start"] <= global_page < f["start"] + f["pages"]:
            return f, global_page - f["start"] + 1
    return None, None


def done_pages() -> set[int]:
    """Global page indices already fetched, from every raw JSONL under data/t5/."""
    done: set[int] = set()
    if not T5_DIR.exists():
        return done
    for f in T5_DIR.rglob("*.jsonl"):
        try:
            with f.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    done.add(d["global_page"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return done


def _write_progress(worker_id: int, fields: dict) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROGRESS_DIR / f"worker_{worker_id:02d}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(fields), encoding="utf-8")
    tmp.replace(path)


def worker(
    worker_id: int,
    facets: list[dict],
    effective: list[int],
    next_index,
    period: float,
    stagger: float,
    proxy: str | None = None,
    report_interval: float = 5.0,
) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f"worker_{worker_id:02d}.jsonl"
    total = len(effective)

    if proxy:
        os.environ["https_proxy"] = proxy
        os.environ["http_proxy"] = proxy
    egress_ip = _egress_ip() if proxy else None

    session = GemSession()
    session.refresh()

    pages_done = 0
    docs_fetched = 0
    errors = 0
    backoffs = 0
    facet_counts: dict[str, int] = {f["label"]: 0 for f in facets}
    started_ts = _now()
    t0 = time.monotonic()

    def emit(status: str, page: int | None) -> None:
        elapsed = time.monotonic() - t0
        _write_progress(
            worker_id,
            {
                "worker_id": worker_id,
                "status": status,
                "pages_total": total,
                "pages_done": pages_done,
                "docs_fetched": docs_fetched,
                "errors": errors,
                "backoffs": backoffs,
                "rate": pages_done / elapsed if elapsed > 0 else 0.0,
                "current_page": page,
                "facet_counts": facet_counts,
                "started_ts": started_ts,
                "last_update_ts": _now(),
                "proxy": _mask_proxy(proxy),
                "egress_ip": egress_ip,
            },
        )

    time.sleep(worker_id * stagger)  # phase offset -> requests roll in every stagger

    raw_f = raw_path.open("a", encoding="utf-8")
    backoff = 0.0
    current_page: int | None = None
    last_emit = 0.0
    try:
        while True:
            if STOP_FILE.exists():
                emit("stopped", page=current_page)
                return
            # Pull the next global page off the shared cursor (work-stealing).
            # Fast workers keep drawing while slow ones are still in flight, so no
            # worker idles before the whole queue is drained.
            with next_index.get_lock():
                i = next_index.value
                next_index.value += 1
            if i >= total:
                break
            g = effective[i]
            facet, page = resolve_page(facets, g)
            if facet is None:
                pages_done += 1
                continue
            current_page = page
            ok, nf, doclist = session.post_page_with_retry(
                "",
                page,
                sort=SORT,
                status=facet["status"],
                by_status=facet["by_status"],
            )
            if ok:
                raw_f.write(
                    json.dumps(
                        {
                            "filter": facet["label"],
                            "page": page,
                            "global_page": g,
                            "num_found": nf,
                            "fetched_ts": _now(),
                            "docs": doclist,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                raw_f.flush()
                docs_fetched += len(doclist)
                facet_counts[facet["label"]] += 1
                backoff = 0.0
            else:
                errors += 1
                backoffs += 1
                backoff = BACKOFF_BASE if backoff == 0.0 else min(BACKOFF_MAX, backoff * 2)
            pages_done += 1
            # Time-based reporting: update progress at least every report_interval
            # seconds (plus the first few pages), so the dashboard stays fresh even
            # on slow deep pages where a page-count threshold would lag badly.
            now = time.monotonic()
            if pages_done <= 5 or now - last_emit >= report_interval:
                emit("running", page=page)
                last_emit = now
            time.sleep(backoff if backoff else period)
    finally:
        raw_f.close()
    emit("done", page=current_page)


def run(
    n_workers: int = 10,
    max_pages: int | None = None,
    period: float = DEFAULT_PERIOD,
    stagger: float = DEFAULT_STAGGER,
    report_interval: float = 5.0,
) -> None:
    proxies = load_proxies()
    facets = fetch_facets()
    total = sum(f["pages"] for f in facets)
    done = done_pages()
    remaining = [g for g in range(total) if g not in done]
    effective = remaining[:max_pages] if max_pages else remaining
    # Remaining work per facet (this run's scope), for the dashboard facet view.
    facet_remaining = {f["label"]: 0 for f in facets}
    for g in effective:
        facet, _ = resolve_page(facets, g)
        if facet:
            facet_remaining[facet["label"]] += 1
    summary = {
        "facets": [
            {
                **{k: f[k] for k in ("label", "num_found", "pages", "start")},
                "remaining": facet_remaining[f["label"]],
            }
            for f in facets
        ],
        "total_pages": total,
        "done_pages": len(done),
        "remaining_pages": len(remaining),
        "scraping_pages": len(effective),
        "n_workers": n_workers,
        "period": period,
        "stagger": stagger,
        "proxies": len(proxies),
        "started_ts": _now(),
    }
    print(json.dumps(summary, indent=2))
    (T5_DIR / "run.json").write_text(json.dumps(summary), encoding="utf-8")
    STOP_FILE.unlink(missing_ok=True)

    # Progress files are ephemeral dashboard state; resume reads the raw jsonl, so
    # clear stale workers from a prior run before spawning fresh ones.
    for p in PROGRESS_DIR.glob("worker_*.json"):
        p.unlink(missing_ok=True)

    # Shared atomic work cursor: workers pull the next global page off it until
    # exhausted, so a worker that finishes early keeps helping instead of idling.
    # This replaces static contiguous chunking, which left fast workers idle after
    # finishing their slice while slow (deep-pagination) workers ground on alone.
    next_index = multiprocessing.Value("q", 0)

    procs = []
    for i in range(n_workers):
        proxy = proxies[i % len(proxies)] if proxies else None
        p = multiprocessing.Process(
            target=worker,
            args=(i, facets, effective, next_index, period, stagger, proxy, report_interval),
        )
        p.start()
        procs.append(p)
    for p in procs:
        p.join()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="t5", description="T5 fast parallel raw snapshot")
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--max-pages", type=int, default=None, help="total pages (default: all)")
    ap.add_argument("--period", type=float, default=DEFAULT_PERIOD)
    ap.add_argument("--stagger", type=float, default=DEFAULT_STAGGER)
    ap.add_argument(
        "--report-interval",
        type=float,
        default=5.0,
        help="progress-file update interval in seconds (dashboard freshness)",
    )
    ap.add_argument("--test", action="store_true", help="tiny smoke run")
    args = ap.parse_args(argv)
    pages = 20 if args.test else args.max_pages
    run(args.workers, pages, args.period, args.stagger, args.report_interval)


if __name__ == "__main__":
    main()
