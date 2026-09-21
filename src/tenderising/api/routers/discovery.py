"""Discovery: filtered, sortable, paginated bid search + facets + CSV export."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from tenderising.api import schemas
from tenderising.api.deps import SkillsDep, parse_dt
from tenderising.db.models import Bid, BuyerOrg

router = APIRouter(prefix="/api/search", tags=["discovery"])
export_router = APIRouter(prefix="/api/export", tags=["discovery"])


def bid_filters(
    q: str | None = None,
    status: str = "ongoing",
    ministry: str | None = None,
    department: str | None = None,
    organization: str | None = None,
    category: str | None = None,
    is_high_value: bool | None = None,
    has_boq: bool | None = None,
    has_documents: bool | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    end_after: str | None = None,
    end_before: str | None = None,
) -> dict:
    return {
        "q": q,
        "status": status,
        "ministry": ministry,
        "department": department,
        "organization": organization,
        "category": category,
        "is_high_value": is_high_value,
        "has_boq": has_boq,
        "has_documents": has_documents,
        "published_after": parse_dt(published_after),
        "published_before": parse_dt(published_before),
        "end_after": parse_dt(end_after),
        "end_before": parse_dt(end_before),
    }


@router.get("/bids")
def search_bids(
    filters: Annotated[dict, Depends(bid_filters)],
    skills: SkillsDep,
    sort: str | None = None,
    sort_dir: str = "asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    result = skills.search_bids(
        **filters, sort=sort, sort_dir=sort_dir, limit=limit, offset=offset
    )
    return {
        "total": result["count"],
        "limit": limit,
        "offset": offset,
        "bids": [schemas.public_bid(b) for b in result["bids"]],
    }


@router.get("/facets")
def facets(skills: SkillsDep) -> dict:
    s = skills.store.session
    ministries = [
        r[0]
        for r in s.query(BuyerOrg.name)
        .filter(BuyerOrg.level == "ministry")
        .distinct()
        .order_by(BuyerOrg.name)
        .all()
    ]
    departments = [
        r[0]
        for r in s.query(BuyerOrg.name)
        .filter(BuyerOrg.level == "department")
        .distinct()
        .order_by(BuyerOrg.name)
        .all()
    ]
    categories = [
        r[0]
        for r in s.query(Bid.category_name)
        .filter(Bid.category_name.isnot(None))
        .distinct()
        .order_by(Bid.category_name)
        .limit(500)
        .all()
    ]
    statuses = [
        r[0]
        for r in s.query(Bid.status_normalized)
        .filter(Bid.status_normalized.isnot(None))
        .distinct()
        .all()
    ]
    return {
        "ministries": ministries,
        "departments": departments,
        "categories": categories,
        "statuses": statuses,
        "unavailable": ["value", "emd", "state", "city"],
    }


@export_router.get("/bids")
def export_bids(
    filters: Annotated[dict, Depends(bid_filters)],
    skills: SkillsDep,
) -> Response:
    result = skills.search_bids(**filters, limit=10000, offset=0)
    out = io.StringIO()
    writer = csv.writer(out)
    fields = [
        "bid_number",
        "category_name",
        "status",
        "ministry",
        "department",
        "end_date",
        "total_quantity",
        "is_high_value",
        "has_boq",
        "has_documents",
    ]
    writer.writerow(fields)
    for b in result["bids"]:
        p = schemas.public_bid(b)
        writer.writerow([p[f] for f in fields])
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="bids.csv"'},
    )
