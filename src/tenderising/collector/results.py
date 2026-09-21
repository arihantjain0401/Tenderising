"""Bid result collector: getBidResultView/<b_id> -> participation + award.

The result view is server-rendered (revalidated 2026-09-19): a technical table
(Seller Name / Status = Qualified/Disqualified) and a financial table
(Seller Name / Total Price / Rank = L1..Ln). L1 feeds participation + award as a
separate fact (§4.2); absence of a seller is never inferred.
"""

from __future__ import annotations

import html as _html
import re

from tenderising.config import BID_TYPE_RA, GET_BID_RESULT_VIEW, Stage
from tenderising.db.models import Bid
from tenderising.service.invariants import normalize_price
from tenderising.service.store import CuratedStoreService

_TAG = re.compile(r"<[^>]+>")


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(_TAG.sub(" ", text))).strip()


def _parse_tables(html_text: str) -> tuple[list[list[str]], ...]:
    tables = re.findall(r"<table.*?</table>", html_text, re.S | re.I)
    parsed = []
    for tab in tables:
        rows = []
        for tr in re.findall(r"<tr.*?</tr>", tab, re.S | re.I):
            cells = [_cell(c) for c in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S | re.I)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if rows:
            parsed.append(rows)
    return tuple(parsed)


def _index_of(header: list[str], key: str, default: int | None = None) -> int | None:
    for i, c in enumerate(header):
        if key in c.lower():
            return i
    return default


def _exact_index(header: list[str], key: str) -> int | None:
    for i, c in enumerate(header):
        if c.lower().strip() == key:
            return i
    return None


def parse_result_view(html_text: str) -> tuple[list[dict], list[dict]]:
    technical: list[dict] = []
    financial: list[dict] = []
    for rows in _parse_tables(html_text):
        header = [c.lower() for c in rows[0]]
        joined = " ".join(header)
        if "seller name" not in joined:
            continue
        if "total price" in joined and "rank" in joined:
            si = _index_of(header, "seller name", 1)
            ti = _index_of(header, "total price")
            ri = _index_of(header, "rank")
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                financial.append(
                    {
                        "seller_name": r[si] if si is not None and si < len(r) else None,
                        "total_price": normalize_price(r[ti])
                        if ti is not None and ti < len(r)
                        else None,
                        "rank": r[ri] if ri is not None and ri < len(r) else None,
                    }
                )
        elif "status" in joined and "seller name" in joined:
            si = _index_of(header, "seller name", 1)
            sti = _exact_index(header, "status")
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                technical.append(
                    {
                        "seller_name": r[si] if si is not None and si < len(r) else None,
                        "status": r[sti] if sti is not None and sti < len(r) else None,
                    }
                )
    return technical, financial


class ResultCollector:
    def __init__(self, session, store: CuratedStoreService):
        self.session = session
        self.store = store

    def collect(self, bid: Bid) -> dict:
        url = GET_BID_RESULT_VIEW + bid.b_id
        status, _ct, html = self.session.get(url)
        if status != 200 or not html:
            return {"technical": 0, "financial": 0}
        raw_ref = self.store.write_raw_evidence("html", html)
        technical, financial = parse_result_view(html.decode("utf-8", "replace"))

        for row in technical:
            seller_id = self.store.get_or_create_seller(row["seller_name"])
            if seller_id is None:
                continue
            self.store.record_participation(
                bid_id=bid.id,
                seller_id=seller_id,
                stage=Stage.TECHNICAL.value,
                result=row["status"],
                source_url=url,
                raw_ref=raw_ref,
            )

        l1 = None
        for row in financial:
            seller_id = self.store.get_or_create_seller(row["seller_name"])
            if seller_id is None:
                continue
            self.store.record_participation(
                bid_id=bid.id,
                seller_id=seller_id,
                stage=Stage.FINANCIAL.value,
                result=row["rank"],
                total_price=row["total_price"],
                source_url=url,
                raw_ref=raw_ref,
            )
            if row["rank"] == "L1":
                l1 = row

        if l1:
            seller_id = self.store.get_or_create_seller(l1["seller_name"])
            source = "ra_award" if bid.bid_type == BID_TYPE_RA else "bid_award"
            self.store.record_award(
                source=source,
                bid_id=bid.id,
                l1_seller_id=seller_id,
                awarded_value=l1["total_price"],
                source_url=url,
                raw_ref=raw_ref,
            )

        return {"technical": len(technical), "financial": len(financial)}
