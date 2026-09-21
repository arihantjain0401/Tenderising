"""Read-only skills over the curated DB (exposed by the service layer, not MCP).

These are the query methods a future MCP/HTTP wrapper would call. Reads only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_

from tenderising.config import BID_STATUS_ACTIVE
from tenderising.db.models import (
    Award,
    Bid,
    BidCorrigendum,
    BidDocument,
    BidLineItem,
    BuyerOrg,
    ChangeEvent,
    CollectionRun,
    Participation,
    Seller,
)
from tenderising.service.store import CuratedStoreService


def _as_dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class _BuyerIndex:
    """In-memory buyer-hierarchy index for cheap chain lookups and SQL-side filtering.

    Replaces the old per-bid ``_org_names`` DB walk (an N+1 over every result row)
    with one load + O(1) chain lookup, and resolves descendant id sets for filtering.
    Stays correct as organisation/office nodes arrive (§4.10 — never flatten).
    """

    def __init__(self, session) -> None:
        rows = session.query(BuyerOrg).all()
        self._by_id = {r.id: r for r in rows}
        self._children: dict[int | None, list[int]] = {}
        for r in rows:
            self._children.setdefault(r.parent_id, []).append(r.id)

    def chain(self, node_id: int | None) -> dict:
        out = {"ministry": None, "department": None, "organisation": None, "office": None}
        path: list[tuple[str, str]] = []
        cur = node_id
        seen: set[int] = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            node = self._by_id.get(cur)
            if node is None:
                break
            path.append((node.level, node.name))
            cur = node.parent_id
        for level, name in reversed(path):
            if level in out:
                out[level] = name
        return out

    def descendant_ids(
        self, name: str, level: str | None = None, substring: bool = False
    ) -> list[int]:
        needle = name.lower()
        matched = [
            r.id
            for r in self._by_id.values()
            if (level is None or r.level == level)
            and (
                needle in (r.name or "").lower()
                if substring
                else (r.name or "").lower() == needle
            )
        ]
        result: set[int] = set()
        stack = list(matched)
        while stack:
            node_id = stack.pop()
            if node_id in result:
                continue
            result.add(node_id)
            stack.extend(self._children.get(node_id, []))
        return list(result)


class Skills:
    def __init__(self, store: CuratedStoreService):
        self.store = store

    def _filtered_query(
        self,
        q: str | None = None,
        status: str = "ongoing",
        ministry: str | None = None,
        department: str | None = None,
        organization: str | None = None,
        category: str | None = None,
        bid_type: str | None = None,
        is_high_value: bool | None = None,
        has_boq: bool | None = None,
        has_documents: bool | None = None,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
        end_after: datetime | None = None,
        end_before: datetime | None = None,
    ):
        s = self.store.session
        query = s.query(Bid)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Bid.bid_number.ilike(like), Bid.category_name.ilike(like)))
        if status == "ongoing":
            query = query.filter(Bid.b_status_raw == BID_STATUS_ACTIVE)
        elif status == "closed":
            query = query.filter(Bid.b_status_raw != BID_STATUS_ACTIVE)
        if category:
            query = query.filter(Bid.category_name.ilike(f"%{category}%"))
        if bid_type:
            query = query.filter(Bid.bid_type == bid_type)
        if is_high_value is not None:
            query = query.filter(Bid.is_high_value.is_(is_high_value))
        if has_boq is not None:
            exists = (
                s.query(BidDocument.id)
                .filter(BidDocument.bid_id == Bid.id, BidDocument.doc_type == "BOQ")
                .exists()
            )
            query = query.filter(exists if has_boq else ~exists)
        if has_documents is not None:
            exists = s.query(BidDocument.id).filter(BidDocument.bid_id == Bid.id).exists()
            query = query.filter(exists if has_documents else ~exists)
        if published_after:
            query = query.filter(Bid.start_date >= published_after)
        if published_before:
            query = query.filter(Bid.start_date <= published_before)
        if end_after:
            query = query.filter(Bid.end_date >= end_after)
        if end_before:
            query = query.filter(Bid.end_date <= end_before)

        idx = _BuyerIndex(self.store.session)
        if ministry:
            query = query.filter(
                Bid.office_id.in_(idx.descendant_ids(ministry, level="ministry") or [0])
            )
        if department:
            query = query.filter(
                Bid.office_id.in_(idx.descendant_ids(department, level="department") or [0])
            )
        if organization:
            query = query.filter(
                Bid.office_id.in_(idx.descendant_ids(organization, substring=True) or [0])
            )
        return query

    def search_bids(
        self,
        q: str | None = None,
        status: str = "ongoing",
        ministry: str | None = None,
        department: str | None = None,
        organization: str | None = None,
        category: str | None = None,
        bid_type: str | None = None,
        is_high_value: bool | None = None,
        has_boq: bool | None = None,
        has_documents: bool | None = None,
        published_after: datetime | None = None,
        published_before: datetime | None = None,
        end_after: datetime | None = None,
        end_before: datetime | None = None,
        sort: str | None = None,
        sort_dir: str = "asc",
        limit: int = 500,
        offset: int = 0,
    ) -> dict:
        s = self.store.session
        query = self._filtered_query(
            q=q,
            status=status,
            ministry=ministry,
            department=department,
            organization=organization,
            category=category,
            bid_type=bid_type,
            is_high_value=is_high_value,
            has_boq=has_boq,
            has_documents=has_documents,
            published_after=published_after,
            published_before=published_before,
            end_after=end_after,
            end_before=end_before,
        )
        total = query.count()

        order_map = {
            "deadline": Bid.end_date,
            "status": Bid.status_normalized,
            "category": Bid.category_name,
            "quantity": Bid.total_quantity,
            "published": Bid.start_date,
        }
        order_col = order_map.get(sort) if sort else None
        if order_col is not None:
            query = query.order_by(
                order_col.asc() if sort_dir == "asc" else order_col.desc(), Bid.id.desc()
            )
        else:
            query = query.order_by(Bid.end_date.is_(None), Bid.end_date.asc(), Bid.id.desc())

        rows = query.offset(offset).limit(limit).all()

        boq_ids = {
            r[0]
            for r in s.query(BidDocument.bid_id).filter(BidDocument.doc_type == "BOQ").all()
        }
        doc_ids = {r[0] for r in s.query(BidDocument.bid_id).all()}

        idx = _BuyerIndex(s)
        bids = []
        for bid in rows:
            d = _as_dict(bid)
            d.update(idx.chain(bid.office_id))
            d["url"] = "https://bidplus.gem.gov.in/showbidDocument/" + (bid.b_id or "")
            d["has_boq"] = bid.id in boq_ids
            d["has_documents"] = bid.id in doc_ids
            bids.append(d)
        return {"count": total, "bids": bids}

    def deadline_histogram(self, **filters) -> list[dict]:
        base = self._filtered_query(**filters)
        now = datetime.now(UTC).replace(tzinfo=None)
        d7 = now + timedelta(days=7)
        d30 = now + timedelta(days=30)
        d90 = now + timedelta(days=90)

        def _count(*fs):
            q = base
            for f in fs:
                q = q.filter(f)
            return q.count()

        return [
            {"bucket": "overdue", "count": _count(Bid.end_date.isnot(None), Bid.end_date < now)},
            {"bucket": "this_week", "count": _count(Bid.end_date >= now, Bid.end_date < d7)},
            {"bucket": "next_30d", "count": _count(Bid.end_date >= d7, Bid.end_date < d30)},
            {"bucket": "30_90d", "count": _count(Bid.end_date >= d30, Bid.end_date < d90)},
            {"bucket": "90d_plus", "count": _count(Bid.end_date >= d90)},
            {"bucket": "no_date", "count": _count(Bid.end_date.is_(None))},
        ]

    def top_departments(self, **filters) -> list[dict]:
        base = self._filtered_query(**filters)
        rows = (
            base.join(BuyerOrg, Bid.office_id == BuyerOrg.id)
            .with_entities(BuyerOrg.name, func.count(Bid.id))
            .group_by(BuyerOrg.name)
            .order_by(func.count(Bid.id).desc())
            .limit(8)
            .all()
        )
        return [{"department": n, "count": c} for n, c in rows]

    def scoped_insights(self, **filters) -> dict:
        s = self.store.session
        base = self._filtered_query(**filters)
        now = datetime.now(UTC).replace(tzinfo=None)
        d7 = now + timedelta(days=7)
        boq_exists = (
            s.query(BidDocument.id)
            .filter(BidDocument.bid_id == Bid.id, BidDocument.doc_type == "BOQ")
            .exists()
        )
        return {
            "total": base.count(),
            "high_value": base.filter(Bid.is_high_value.is_(True)).count(),
            "with_boq": base.filter(boq_exists).count(),
            "closing_7d": base.filter(
                Bid.end_date.isnot(None), Bid.end_date >= now, Bid.end_date < d7
            ).count(),
        }

    def get_changes(
        self, since: datetime | None = None, kinds: list[str] | None = None, limit: int = 1000
    ) -> dict:
        since = since or (datetime.now(UTC) - timedelta(hours=24))
        want = set(kinds or ["new", "modified"])
        events: list[dict] = []

        if "new" in want:
            new_bids = (
                self.store.session.query(Bid)
                .filter(Bid.first_seen >= since)
                .order_by(Bid.first_seen.desc())
                .limit(limit)
                .all()
            )
            for bid in new_bids:
                events.append(
                    {
                        "kind": "new",
                        "ts": bid.first_seen,
                        "bid_id": bid.b_id,
                        "bid_number": bid.bid_number,
                    }
                )

        if "modified" in want:
            changes = (
                self.store.session.query(ChangeEvent)
                .filter(ChangeEvent.new_retrieval_ts >= since)
                .order_by(ChangeEvent.new_retrieval_ts.desc())
                .limit(limit)
                .all()
            )
            for ev in changes:
                events.append(
                    {
                        "kind": "modified",
                        "ts": ev.new_retrieval_ts,
                        "entity_id": ev.entity_id,
                        "field": ev.field,
                        "prior": ev.prior_value,
                        "new": ev.new_value,
                    }
                )

        events.sort(key=lambda e: e["ts"], reverse=True)
        events = events[:limit]
        return {"count": len(events), "since": since, "events": events}

    def get_bid_detail(self, b_id: str | None = None, bid_number: str | None = None) -> dict | None:
        s = self.store.session
        q = s.query(Bid)
        bid = None
        if b_id:
            bid = q.filter(Bid.b_id == b_id).first()
        if bid is None and bid_number:
            bid = q.filter(Bid.bid_number == bid_number).first()
        if bid is None:
            return None

        idx = _BuyerIndex(s)
        detail = _as_dict(bid)
        detail.update(idx.chain(bid.office_id))
        detail["corrigenda"] = [
            _as_dict(c)
            for c in s.query(BidCorrigendum).filter(BidCorrigendum.bid_id == bid.id).all()
        ]
        detail["documents"] = [
            _as_dict(d) for d in s.query(BidDocument).filter(BidDocument.bid_id == bid.id).all()
        ]
        detail["line_items"] = [
            _as_dict(it)
            for it in s.query(BidLineItem)
            .join(BidDocument, BidLineItem.document_id == BidDocument.id)
            .filter(BidDocument.bid_id == bid.id)
            .all()
        ]
        detail["participation"] = [
            {**_as_dict(p), "firm_name": firm_name}
            for p, firm_name in s.query(Participation, Seller.firm_name)
            .join(Seller, Participation.seller_id == Seller.id)
            .filter(Participation.bid_id == bid.id)
            .all()
        ]
        award = s.query(Award).filter(Award.bid_id == bid.id).first()
        if award is not None:
            a = _as_dict(award)
            l1 = s.query(Seller.firm_name).filter(Seller.id == award.l1_seller_id).first()
            a["l1_seller_name"] = l1[0] if l1 else None
            detail["award"] = a
        else:
            detail["award"] = None
        return detail

    def get_stats(self) -> dict:
        s = self.store.session
        total = s.query(Bid).count()
        active = s.query(Bid).filter(Bid.b_status_raw == BID_STATUS_ACTIVE).count()
        week = datetime.now(UTC) - timedelta(days=7)
        new_7d = s.query(Bid).filter(Bid.first_seen >= week).count()
        modified_7d = s.query(ChangeEvent).filter(ChangeEvent.new_retrieval_ts >= week).count()
        last_runs = s.query(CollectionRun).order_by(CollectionRun.id.desc()).limit(10).all()
        return {
            "total_bids": total,
            "active_bids": active,
            "new_7d": new_7d,
            "modified_7d": modified_7d,
            "last_runs": [_as_dict(r) for r in last_runs],
        }
