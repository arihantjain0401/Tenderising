"""Public DTOs — the single choke-point that strips internal fields before anything
leaves the API.

Never expose b_id, office_id, raw status, fingerprints, provenance timestamps, or
crawler flags to customers. Status is mapped to a friendly label; source is a label,
not an internal URL.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tenderising.config import BID_STATUS_ACTIVE

# A bid that ends within this many days is shown to customers as "Closing soon".
CLOSING_SOON_DAYS = 7


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _to_aware(value) -> datetime | None:
    """Coerce a datetime or ISO string to an aware UTC datetime (or None)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _status_label(d: dict) -> str:
    """Customer-facing status (§§4.6/4.7): derived from the internal buyer status,
    the active/closed flag, and the deadline — the internal ``status_normalized``
    ("Not Evaluated", etc.) is never shown verbatim to customers.
    """
    norm = (d.get("status_normalized") or "").strip()
    if norm == "Bid Award":
        return "Awarded"

    b_status = d.get("b_status_raw")
    if b_status is None:
        return "Status unavailable"
    if str(b_status) != BID_STATUS_ACTIVE:
        return "Closed"

    end = _to_aware(d.get("end_date"))
    if end is not None:
        now = datetime.now(UTC)
        if now <= end <= now + timedelta(days=CLOSING_SOON_DAYS):
            return "Closing soon"
    return "Open"


def public_bid(d: dict) -> dict:
    return {
        "bid_number": d.get("bid_number"),
        "category_name": d.get("category_name"),
        "status": _status_label(d),
        "is_high_value": d.get("is_high_value"),
        "total_quantity": d.get("total_quantity"),
        "start_date": _iso(d.get("start_date")),
        "end_date": _iso(d.get("end_date")),
        "ministry": d.get("ministry"),
        "department": d.get("department"),
        "organisation": d.get("organisation"),
        "office": d.get("office"),
        "last_verified": _iso(d.get("last_seen")),
        "has_boq": bool(d.get("has_boq")),
        "has_documents": bool(d.get("has_documents")),
    }


def public_corrigendum(c: dict) -> dict:
    return {
        "corrigendum_no": c.get("corrigendum_no"),
        "issue_date": _iso(c.get("issue_date")),
        "summary": c.get("summary"),
    }


def public_document(doc: dict) -> dict:
    return {
        "id": doc.get("id"),
        "doc_type": doc.get("doc_type"),
        "title": doc.get("title"),
        "page_count": doc.get("page_count"),
        "byte_size": doc.get("byte_size"),
        "content_type": doc.get("content_type"),
        "disclosure_state": doc.get("disclosure_state"),
        "download_url": f"/api/documents/{doc['id']}/download" if doc.get("id") else None,
    }


def public_line_item(it: dict) -> dict:
    return {
        "item_no": it.get("item_no"),
        "description": it.get("description"),
        "quantity": it.get("quantity"),
        "unit": it.get("unit"),
        "unit_price": it.get("unit_price"),
        "total_price": it.get("total_price"),
        "consignee": it.get("consignee"),
    }


def public_participation(p: dict) -> dict:
    return {
        "stage": p.get("stage"),
        "firm_name": p.get("firm_name"),
        "result": p.get("result"),
        "total_price": p.get("total_price"),
    }


def public_award(a: dict | None) -> dict | None:
    if a is None:
        return None
    return {
        "source": a.get("source"),
        "awarded_value": a.get("awarded_value"),
        "award_date": _iso(a.get("award_date")),
        "l1_seller_name": a.get("l1_seller_name"),
        "status": a.get("status"),
    }


def public_bid_detail(d: dict) -> dict:
    return {
        "bid_number": d.get("bid_number"),
        "category_name": d.get("category_name"),
        "status": _status_label(d),
        "is_high_value": d.get("is_high_value"),
        "total_quantity": d.get("total_quantity"),
        "start_date": _iso(d.get("start_date")),
        "end_date": _iso(d.get("end_date")),
        "ministry": d.get("ministry"),
        "department": d.get("department"),
        "organisation": d.get("organisation"),
        "office": d.get("office"),
        "last_verified": _iso(d.get("last_seen")),
        "corrigenda": [public_corrigendum(c) for c in d.get("corrigenda", [])],
        "documents": [public_document(doc) for doc in d.get("documents", [])],
        "line_items": [public_line_item(it) for it in d.get("line_items", [])],
        "participation": [public_participation(p) for p in d.get("participation", [])],
        "award": public_award(d.get("award")),
    }
