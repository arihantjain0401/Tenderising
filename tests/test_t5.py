"""Unit tests for T5 work distribution: exactly-once fetch, per-facet counts."""

from __future__ import annotations

import json
import multiprocessing
import threading
import time

from tenderising.schedule import t5


class FakeSession:
    """Stand-in for GemSession — no network, tiny sleep to force interleaving."""

    def refresh(self) -> None:
        pass

    def post_page_with_retry(self, keyword: str, page: int, **kwargs):
        time.sleep(0.002)
        return True, 100, [{"id": f"d{page}"} for _ in range(10)]


def _facets() -> list[dict]:
    return [
        {
            "label": "awarded",
            "status": "bidrastatus",
            "by_status": "bid_awarded",
            "num_found": 100,
            "pages": 10,
            "start": 0,
        },
        {
            "label": "financial-evaluated",
            "status": "bidrastatus",
            "by_status": "fin_evaluated",
            "num_found": 50,
            "pages": 5,
            "start": 10,
        },
    ]


def test_resolve_page_boundaries():
    facets = _facets()
    # awarded covers global 0..9; financial 10..14.
    assert t5.resolve_page(facets, 0) == (facets[0], 1)
    assert t5.resolve_page(facets, 9) == (facets[0], 10)
    assert t5.resolve_page(facets, 10) == (facets[1], 1)
    assert t5.resolve_page(facets, 14) == (facets[1], 5)
    assert t5.resolve_page(facets, 15) == (None, None)


def test_worker_steals_and_drains_exactly_once(tmp_path, monkeypatch):
    monkeypatch.setattr(t5, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(t5, "PROGRESS_DIR", tmp_path / "progress")
    monkeypatch.setattr(t5, "STOP_FILE", tmp_path / "stop")
    monkeypatch.setattr(t5, "GemSession", FakeSession)

    facets = _facets()
    effective = list(range(15))  # 15 global pages to distribute
    next_index = multiprocessing.Value("q", 0)

    # Two workers run concurrently (threads) pulling off the shared cursor.
    threads = [
        threading.Thread(
            target=t5.worker, args=(i, facets, effective, next_index, 0.0, 0.0)
        )
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Every global page must be fetched exactly once across all workers.
    seen: set[int] = set()
    for p in (tmp_path / "raw").glob("worker_*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            seen.add(json.loads(line)["global_page"])
    assert seen == set(range(15))

    # Per-worker progress files finish "done" and carry correct per-facet counts.
    counts: dict[str, int] = {}
    for p in (tmp_path / "progress").glob("worker_*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["status"] == "done"
        for k, v in d["facet_counts"].items():
            counts[k] = counts.get(k, 0) + v
    assert counts == {"awarded": 10, "financial-evaluated": 5}
