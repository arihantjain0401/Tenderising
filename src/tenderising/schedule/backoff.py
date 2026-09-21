"""Per-bid backoff (§7): interval grows on quiet stretches, resets on change."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tenderising.db.models import BidPollState
from tenderising.db.models.base import utcnow

BASE_INTERVAL_SECONDS = 3600  # 1 hour
MAX_INTERVAL_SECONDS = 7 * 24 * 3600  # 7 days
GROWTH_FACTOR = 2.0


def update_poll_state(store, bid_id: int, *, changed: bool) -> BidPollState:
    state = store.session.query(BidPollState).filter(BidPollState.bid_id == bid_id).first()
    now = utcnow()
    if state is None:
        state = BidPollState(
            bid_id=bid_id,
            poll_interval_seconds=BASE_INTERVAL_SECONDS,
            consecutive_no_change=0,
            updated_ts=now,
        )
        store.session.add(state)
    if changed:
        state.poll_interval_seconds = BASE_INTERVAL_SECONDS
        state.consecutive_no_change = 0
    else:
        state.consecutive_no_change += 1
        state.poll_interval_seconds = min(
            int(state.poll_interval_seconds * GROWTH_FACTOR), MAX_INTERVAL_SECONDS
        )
    state.next_poll_at = now + timedelta(seconds=state.poll_interval_seconds)
    state.updated_ts = now
    return state


def due_bid_ids(store, *, now: datetime | None = None, limit: int = 200) -> list[int]:
    now = now or datetime.now(UTC)
    rows = (
        store.session.query(BidPollState)
        .filter(BidPollState.next_poll_at <= now)
        .order_by(BidPollState.next_poll_at)
        .limit(limit)
        .all()
    )
    return [r.bid_id for r in rows]
