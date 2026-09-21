"""LiveFetchService — on-demand fetch + enrichment (documents, results)."""

from __future__ import annotations

from tenderising.collector.bids import BidCollector
from tenderising.collector.corrigenda import CorrigendumCollector
from tenderising.collector.documents import DocumentCollector
from tenderising.collector.results import ResultCollector
from tenderising.collector.session import GemSession
from tenderising.db.models import Bid
from tenderising.service.store import CuratedStoreService


class LiveFetchService:
    def __init__(self):
        self.session = GemSession()
        self.session.refresh()
        self.store = CuratedStoreService()
        self.bids = BidCollector(self.session, self.store)
        self.documents = DocumentCollector(self.session, self.store)
        self.results = ResultCollector(self.session, self.store)
        self.corrigenda = CorrigendumCollector(self.session, self.store)

    def fetch_bid(self, bid_number: str) -> Bid | None:
        ok, _nf, docs = self.session.post_page_with_retry(bid_number, 1)
        if not ok:
            return None
        for doc in docs:
            num = doc.get("b_bid_number")
            num = num[0] if isinstance(num, list) and num else num
            if str(num) == bid_number:
                bid_id, _created, _changed = self.bids.ingest_doc(doc)
                self.store.commit()
                return self.store.session.query(Bid).filter(Bid.id == bid_id).first()
        return None

    def enrich(self, bid: Bid) -> dict:
        self.documents.collect(bid)
        result = self.results.collect(bid)
        corrigenda = self.corrigenda.collect(bid)
        self.store.commit()
        return {**result, "corrigenda": len(corrigenda)}

    def close(self) -> None:
        self.store.close()
