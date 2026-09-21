"""Collection infrastructure: runs, raw evidence, change events, poll state (§8.14-16, §7)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from tenderising.db.models.base import Base


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # full|delta|corrigendum|document|on_demand
    scope: Mapped[str | None] = mapped_column(String(256), nullable=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    num_seen: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    num_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class RawEvidence(Base):
    """The raw payload/document is written BEFORE parsing (§6/§10)."""

    __tablename__ = "raw_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # html|json|pdf|api
    payload_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)  # blob/file path
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieval_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChangeEvent(Base):
    """Append-only value history (§4.9/§6/§8.16). Never silently overwritten."""

    __tablename__ = "change_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    prior_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_retrieval_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    new_retrieval_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BidPollState(Base):
    """Per-bid poll bookkeeping (§7): exponential backoff, reset on change."""

    __tablename__ = "bid_poll_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id"), unique=True, index=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    consecutive_no_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
