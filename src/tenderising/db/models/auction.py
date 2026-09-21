"""Auction/award/contract/direct-order tables (§8.5-8). Separate entities, never collapsed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from tenderising.db.models.base import Base, ProvenanceMixin


class ReverseAuction(ProvenanceMixin, Base):
    __tablename__ = "reverse_auctions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ra_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # internal
    ra_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # public
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"), index=True, nullable=True)
    start_ref_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    step_decrement: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_extension_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_raw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Award(ProvenanceMixin, Base):
    __tablename__ = "awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    award_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # internal
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # bid_award | ra_award
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"), index=True, nullable=True)
    ra_id: Mapped[int | None] = mapped_column(
        ForeignKey("reverse_auctions.id"), index=True, nullable=True
    )
    # L1 is a fact on the auction/bid; award is a SEPARATE fact (§4.2).
    l1_seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id"), nullable=True)
    awarded_value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    award_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Contract(ProvenanceMixin, Base):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contract_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # internal
    contract_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # public
    award_id: Mapped[int | None] = mapped_column(ForeignKey("awards.id"), index=True, nullable=True)
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_orgs.id"), nullable=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id"), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DirectOrder(ProvenanceMixin, Base):
    __tablename__ = "direct_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    order_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # direct|l1 purchase
    buyer_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_orgs.id"), nullable=True)
    seller_id: Mapped[int | None] = mapped_column(ForeignKey("sellers.id"), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    items: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
