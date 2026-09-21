"""Corrigendum collector: viewCorrigendum -> corrigendum list + body text.

Anonymous CSRF-only endpoints (revalidated 2026-09-19), no buyer session:
- public-bid-other-details/<b_id>  -> JSON {"corrigendum": bool}
- viewCorrigendum/<b_id>           -> HTML list (iid + "Modified On" per corrigendum)
- getPublicTchtml/<iid>            -> JSON {"bcm_txt": body text}

Corrigenda are append-only (§4.9): dedup by (bid_id, external_id), never overwritten.
"""

from __future__ import annotations

import json
import re

from tenderising.config import GET_PUBLIC_TC_HTML, PUBLIC_BID_OTHER_DETAILS, VIEW_CORRIGENDUM
from tenderising.db.models import Bid
from tenderising.service.invariants import as_iso_datetime
from tenderising.service.store import CuratedStoreService

_TAG = re.compile(r"<[^>]+>")


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", _TAG.sub(" ", text)).strip()


def parse_corrigendum_list(html_text: str) -> list[dict]:
    """Extract [{iid, modified_on}] from the viewCorrigendum HTML."""
    items: list[dict] = []
    for m in re.finditer(r"id=span_(\d+)", html_text):
        iid = m.group(1)
        tail = html_text[m.end() : m.end() + 400]
        dm = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", tail)
        items.append({"iid": iid, "modified_on": dm.group(1) if dm else None})
    return items


class CorrigendumCollector:
    def __init__(self, session, store: CuratedStoreService):
        self.session = session
        self.store = store

    def has_corrigenda(self, b_id: str) -> bool:
        status, _ct, body = self.session.post_form(PUBLIC_BID_OTHER_DETAILS + b_id)
        if status != 200 or not body:
            return False
        try:
            data = json.loads(body.decode("utf-8", "replace"))
            return bool(data.get("response", {}).get("corrigendum"))
        except json.JSONDecodeError:
            return False

    def collect(self, bid: Bid) -> list:
        if not self.has_corrigenda(bid.b_id):
            return []
        status, _ct, body = self.session.post_form(VIEW_CORRIGENDUM + bid.b_id)
        if status != 200 or not body:
            return []
        self.store.write_raw_evidence("html", body)
        items = parse_corrigendum_list(body.decode("utf-8", "replace"))

        created = []
        for n, item in enumerate(items, start=1):
            body_text = self._fetch_body(item["iid"])
            # The body text is a first-class source (§4.11/§6): persist it as raw evidence.
            raw_ref = (
                self.store.write_raw_evidence("html", body_text.encode("utf-8"))
                if body_text
                else None
            )
            corrigendum, is_new = self.store.record_corrigendum(
                bid_id=bid.id,
                external_id=item["iid"],
                corrigendum_no=f"-C{n}",
                issue_date=as_iso_datetime(item["modified_on"]),
                summary=body_text[:500] if body_text else None,
                source_url=VIEW_CORRIGENDUM + bid.b_id,
                raw_ref=raw_ref,
            )
            if is_new:
                created.append(corrigendum)
        return created

    def _fetch_body(self, iid: str) -> str | None:
        status, _ct, body = self.session.post_form(GET_PUBLIC_TC_HTML + iid)
        if status != 200 or not body:
            return None
        try:
            data = json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return None
        txt = data.get("bcm_txt", "")
        return _strip(txt)[:500] or None
