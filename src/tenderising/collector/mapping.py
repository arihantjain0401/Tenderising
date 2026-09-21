"""Map a raw searchBid doc to normalised fields (via §4 coercers).

Field names re-verified 2026-09-19 (docs/revalidation-2026-09-19.md).
"""

from __future__ import annotations

from tenderising.service.invariants import as_bool, as_iso_datetime, normalize_status, unwrap


def _s(value) -> str | None:
    x = unwrap(value)
    return None if x is None else str(x)


def map_bid(doc: dict) -> dict:
    """Return normalised Bid fields (including the bid_number/b_id keys, and
    ministry/department which resolve to buyer_orgs rather than bid columns)."""
    status_raw, status_normalized, map_version = normalize_status(doc.get("b_buyer_status"))
    category_name = _s(doc.get("b_category_name")) or _s(doc.get("bd_category_name"))
    return {
        "bid_number": _s(doc.get("b_bid_number")),
        "b_id": _s(doc.get("b_id")),
        "parent_b_id": _s(doc.get("b_id_parent")),
        "parent_bid_number": _s(doc.get("b_bid_number_parent")),
        "bid_type": _s(doc.get("b_bid_type")),
        "eval_type": _s(doc.get("b_eval_type")),
        "status_raw": status_raw,
        "status_normalized": status_normalized,
        "status_map_version": map_version,
        "b_status_raw": _s(doc.get("b_status")),
        "bid_to_ra": as_bool(doc.get("b_bid_to_ra")),
        "ra_to_bid": _s(doc.get("b_ra_to_bid")),
        "category_id": _s(doc.get("b_cat_id")),
        "category_name": category_name,
        "total_quantity": _s(doc.get("b_total_quantity")),
        "is_high_value": as_bool(doc.get("is_high_value")),
        "is_bunch": as_bool(doc.get("b_is_bunch")),
        "is_custom_item": as_bool(doc.get("b_is_custom_item")),
        "is_inactive": as_bool(doc.get("b_is_inactive")),
        "single_packet": as_bool(doc.get("ba_is_single_packet")),
        "global_tendering": as_bool(doc.get("ba_is_global_tendering")),
        "start_date": as_iso_datetime(doc.get("final_start_date_sort")),
        "end_date": as_iso_datetime(doc.get("final_end_date_sort")),
        "bid_schedule": _s(doc.get("bid_schedule")),
        "ministry": _s(doc.get("ba_official_details_minName")),
        "department": _s(doc.get("ba_official_details_deptName")),
    }
