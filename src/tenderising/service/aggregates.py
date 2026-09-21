"""Aggregation queries powering Discovery summaries and the Ask collage.

Read-only; each function takes a SQLAlchemy Session. Value/EMD histograms are
deliberately absent until the underlying columns exist (surfaced as "not available
yet" facets in Discovery).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from tenderising.config import BID_STATUS_ACTIVE
from tenderising.db.models import Bid, BuyerOrg


def count_by_status(session: Session) -> list[dict]:
    rows = (
        session.query(Bid.status_normalized, func.count(Bid.id))
        .group_by(Bid.status_normalized)
        .order_by(func.count(Bid.id).desc())
        .all()
    )
    return [{"status": label or "Other", "count": count} for label, count in rows]


def count_by_department(session: Session, limit: int = 15) -> list[dict]:
    rows = (
        session.query(BuyerOrg.name, func.count(Bid.id))
        .join(Bid, Bid.office_id == BuyerOrg.id)
        .group_by(BuyerOrg.name)
        .order_by(func.count(Bid.id).desc())
        .limit(limit)
        .all()
    )
    return [{"department": name, "count": count} for name, count in rows]


def count_by_category(session: Session, limit: int = 15) -> list[dict]:
    rows = (
        session.query(Bid.category_name, func.count(Bid.id))
        .filter(Bid.category_name.isnot(None))
        .group_by(Bid.category_name)
        .order_by(func.count(Bid.id).desc())
        .limit(limit)
        .all()
    )
    return [{"category": name, "count": count} for name, count in rows]


def deadline_histogram(session: Session) -> list[dict]:
    now = datetime.now(UTC).replace(tzinfo=None)
    d7 = now + timedelta(days=7)
    d30 = now + timedelta(days=30)
    d90 = now + timedelta(days=90)

    def _count(*filters):
        q = session.query(func.count(Bid.id))
        for f in filters:
            q = q.filter(f)
        return q.scalar()

    return [
        {"bucket": "overdue", "count": _count(Bid.end_date.isnot(None), Bid.end_date < now)},
        {"bucket": "this_week", "count": _count(Bid.end_date >= now, Bid.end_date < d7)},
        {"bucket": "next_30d", "count": _count(Bid.end_date >= d7, Bid.end_date < d30)},
        {"bucket": "30_90d", "count": _count(Bid.end_date >= d30, Bid.end_date < d90)},
        {"bucket": "90d_plus", "count": _count(Bid.end_date >= d90)},
        {"bucket": "no_date", "count": _count(Bid.end_date.is_(None))},
    ]


def activity_timeline(session: Session, days: int = 30) -> list[dict]:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
    rows = (
        session.query(func.date(Bid.first_seen), func.count(Bid.id))
        .filter(Bid.first_seen >= since)
        .group_by(func.date(Bid.first_seen))
        .order_by(func.date(Bid.first_seen))
        .all()
    )
    return [{"date": str(day), "count": count} for day, count in rows]


def summary(session: Session) -> dict:
    total = session.query(func.count(Bid.id)).scalar()
    active = (
        session.query(func.count(Bid.id)).filter(Bid.b_status_raw == BID_STATUS_ACTIVE).scalar()
    )
    return {
        "total_bids": total,
        "active_bids": active,
        "by_status": count_by_status(session),
        "by_department": count_by_department(session),
        "by_category": count_by_category(session),
        "deadlines": deadline_histogram(session),
    }
