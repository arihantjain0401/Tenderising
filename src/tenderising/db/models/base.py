"""Declarative base and the shared provenance mixin.

Per §8, every observation table carries: source_url, retrieval_ts (UTC),
disclosure_state, parse_status, raw_ref (-> raw_evidence).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tenderising.config import DisclosureState, ParseStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class ProvenanceMixin:
    """Provenance columns attached to every observation row (§8)."""

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    disclosure_state: Mapped[str] = mapped_column(
        String(20), default=DisclosureState.FULL.value, nullable=False
    )
    parse_status: Mapped[str] = mapped_column(
        String(20), default=ParseStatus.PARSED.value, nullable=False
    )
    raw_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # -> raw_evidence.ref_id
