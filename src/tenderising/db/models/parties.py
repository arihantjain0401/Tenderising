"""Buyer/seller/category/participation tables (§8.9-13)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from tenderising.db.models.base import Base, ProvenanceMixin


class Seller(ProvenanceMixin, Base):
    __tablename__ = "sellers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    firm_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Capacity is scoped (seller_capacity_scopes), never one permanent global role (§8.9).
    oem_capacity: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reseller_capacity: Mapped[str | None] = mapped_column(String(256), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(256), nullable=True)
    catalogue_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    authorisation_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    validity_period: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observation_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class SellerCapacityScope(ProvenanceMixin, Base):
    __tablename__ = "seller_capacity_scopes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id"), index=True)
    scope_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # OEM/reseller/service
    category_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    product: Mapped[str | None] = mapped_column(String(256), nullable=True)
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"), index=True, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)


class BuyerOrg(ProvenanceMixin, Base):
    """Hierarchical ministry -> department -> organisation -> office (§4.10/§8.11)."""

    __tablename__ = "buyer_orgs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_orgs.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # ministry|department|org|office
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)


class Category(ProvenanceMixin, Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    category_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    quadrant: Mapped[str | None] = mapped_column(String(8), nullable=True)  # Q1..Q6
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Participation(ProvenanceMixin, Base):
    """A seller's presence at a stage. Absence = no row = missing data (§8.13)."""

    __tablename__ = "participation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id"), index=True)
    stage: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # technical|financial|auction|award
    present: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Enrichment from getBidResultView: result/rank/price are observed, not inferred.
    result: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # Qualified/Disqualified/L1...
    total_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    mse_mii_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
