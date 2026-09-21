"""Bid-centric tables: bids, corrigenda, documents, links, line items (§8.1-4, §8.17)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from tenderising.db.models.base import Base, ProvenanceMixin


class Bid(ProvenanceMixin, Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Public bid number and internal GeM id are different keys (§4.8); keep both.
    bid_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    b_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    parent_b_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    parent_bid_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    bid_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # raw b_bid_type
    eval_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # raw b_eval_type

    # Raw status preserved verbatim, separate from the derived label (§4.7).
    status_raw: Mapped[str | None] = mapped_column(String(16), nullable=True)  # b_buyer_status
    status_normalized: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status_map_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    b_status_raw: Mapped[str | None] = mapped_column(String(16), nullable=True)  # active/closed

    bid_to_ra: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ra_to_bid: Mapped[str | None] = mapped_column(String(32), nullable=True)

    category_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    total_quantity: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_high_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_bunch: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_custom_item: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_inactive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    single_packet: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    global_tendering: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Buyer hierarchy is NOT flattened (§4.10): reference the leaf buyer_orgs node.
    office_id: Mapped[int | None] = mapped_column(ForeignKey("buyer_orgs.id"), nullable=True)

    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tz_uncertain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    bid_schedule: Mapped[str | None] = mapped_column(Text, nullable=True)

    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_algo_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # First/last observation times (provenance for "new" vs "modified").
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BidCorrigendum(ProvenanceMixin, Base):
    __tablename__ = "bid_corrigenda"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bid_id: Mapped[int] = mapped_column(ForeignKey("bids.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # GeM corrigendum id (iid)
    corrigendum_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # -C1, -C2 ...
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    prior_version_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class BidDocument(ProvenanceMixin, Base):
    __tablename__ = "bid_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bid_id: Mapped[int | None] = mapped_column(ForeignKey("bids.id"), index=True, nullable=True)
    corrigendum_id: Mapped[int | None] = mapped_column(
        ForeignKey("bid_corrigenda.id"), index=True, nullable=True
    )
    doc_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # BOQ/GTC/STC/ATC/...
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pdf_signature_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DocumentLink(ProvenanceMixin, Base):
    __tablename__ = "document_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("bid_documents.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    anchor_text: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BidLineItem(ProvenanceMixin, Base):
    __tablename__ = "bid_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("bid_documents.id"), index=True)
    item_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Prices are nullable, never 0 for a missing/masked/unparsed value (§4.6).
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    consignee: Mapped[str | None] = mapped_column(String(256), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
