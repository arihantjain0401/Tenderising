"""Bid listing collector: searchBid -> raw evidence -> curated bids.

Writes raw evidence BEFORE parsing/normalising, then upserts via the service
layer. Dedup by bid_number + b_id + fingerprint; reruns never duplicate.
"""

from __future__ import annotations

import json

from tenderising.collector.fingerprint import bid_fingerprint
from tenderising.collector.mapping import map_bid
from tenderising.collector.session import GemSession
from tenderising.config import FINGERPRINT_ALGO_VERSION, SHOWBID_DOCUMENT
from tenderising.service.store import CuratedStoreService


class BidCollector:
    def __init__(self, session: GemSession, store: CuratedStoreService):
        self.session = session
        self.store = store

    def ingest_doc(self, doc: dict) -> tuple[int | None, bool, bool]:
        """Persist one listing doc. Returns (bid_id, created, changed)."""
        raw_ref = self.store.write_raw_evidence("json", json.dumps(doc).encode("utf-8"))
        fields = map_bid(doc)

        bid_number = fields.pop("bid_number")
        b_id = fields.pop("b_id")
        if not bid_number or not b_id:
            return None, False, False  # no stable key -> skip (missing, not fabricated)

        ministry = fields.pop("ministry")
        department = fields.pop("department")
        fields["office_id"] = self.store.resolve_buyer(ministry, department)

        self.store.get_or_create_category(fields.get("category_id"), fields.get("category_name"))

        fingerprint = bid_fingerprint(fields)
        bid, created, changed = self.store.upsert_bid(
            bid_number=bid_number,
            b_id=b_id,
            fields=fields,
            fingerprint=fingerprint,
            fingerprint_algo_version=FINGERPRINT_ALGO_VERSION,
            source_url=SHOWBID_DOCUMENT + b_id,
            raw_ref=raw_ref,
        )
        return bid.id, created, bool(changed)

    def page(
        self,
        keyword: str,
        page: int,
        *,
        sort: str = "Bid-End-Date-Oldest",
        status: str = "ongoing_bids",
        by_status: str | None = None,
    ) -> tuple[int, list]:
        return self.session.post_page(keyword, page, sort=sort, status=status, by_status=by_status)
