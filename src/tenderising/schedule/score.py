"""Change-probability score (§7) — drives the T1 hot set."""

from __future__ import annotations

from datetime import UTC, datetime

# Pre-award statuses are where change happens.
PRE_AWARD = {"Not Evaluated", "Technical Evaluation", "Financial Evaluation"}


def change_probability_score(bid, now: datetime | None = None) -> float:
    """Higher = more likely to change soon.

    Components (§7): end-date proximity, pre-award status, RA-imminent
    (bid_to_ra), high-value, recency. Corrigendum-recent is folded into
    fingerprint-change recency via the poll backoff rather than re-derived here.
    """
    now = now or datetime.now(UTC)
    score = 0.0

    if bid.end_date is not None:
        end = bid.end_date
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        days = (end - now).total_seconds() / 86400.0
        if days >= 0:
            score += 10.0 / (days + 1.0)  # ending soon => more corrigenda/activity

    if bid.status_normalized in PRE_AWARD:
        score += 5.0
    if bid.bid_to_ra:
        score += 5.0  # RA-imminent bids are the most volatile
    if bid.is_high_value:
        score += 5.0

    return score
