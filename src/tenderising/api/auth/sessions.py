"""Server-side session service (revocable, restart-surviving)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from tenderising.db.models import Session
from tenderising.service.store import CuratedStoreService

SESSION_TTL = timedelta(days=7)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def issue(user_id: int, ip: str | None = None, user_agent: str | None = None) -> str:
    token = secrets.token_urlsafe(32)
    store = CuratedStoreService()
    try:
        store.session.add(
            Session(
                token=token,
                user_id=user_id,
                expires_at=datetime.now(UTC) + SESSION_TTL,
                ip=ip,
                user_agent=user_agent,
            )
        )
        store.commit()
    finally:
        store.close()
    return token


def validate(token: str | None) -> int | None:
    """Return the owning user id, or None if missing/expired (expired rows are purged)."""
    if not token:
        return None
    store = CuratedStoreService()
    try:
        row = store.session.query(Session).filter(Session.token == token).first()
        if row is None:
            return None
        if _aware(row.expires_at) < datetime.now(UTC):
            store.session.delete(row)
            store.commit()
            return None
        return row.user_id
    finally:
        store.close()


def revoke(token: str | None) -> None:
    if not token:
        return
    store = CuratedStoreService()
    try:
        row = store.session.query(Session).filter(Session.token == token).first()
        if row is not None:
            store.session.delete(row)
            store.commit()
    finally:
        store.close()
