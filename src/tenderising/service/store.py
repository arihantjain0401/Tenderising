"""CuratedStoreService — the sole writer to the curated DB.

Encodes §4/§6/§10: raw evidence is persisted before parsing; upserts are keyed on
public+internal id; a fingerprint change appends change_events and never silently
overwrites prior values.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from tenderising.config import DATA_DIR, BuyerLevel
from tenderising.db.engine import SessionLocal
from tenderising.db.models import (
    Award,
    Bid,
    BidCorrigendum,
    BidDocument,
    BidLineItem,
    BuyerOrg,
    Category,
    ChangeEvent,
    DocumentLink,
    Participation,
    RawEvidence,
    Seller,
)
from tenderising.db.models.base import utcnow

RAW_DIR = DATA_DIR / "raw"


def _canon(value):
    """Canonical, comparison-safe form of a stored value.

    SQLite returns timezone-aware datetimes as naive, so compare instants in UTC
    rather than raw str() — otherwise a genuine change would spuriously flag
    start/end_date on every update.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


class CuratedStoreService:
    def __init__(self, session: Session | None = None):
        self.session = session or SessionLocal()

    # -- lifecycle -----------------------------------------------------------
    def commit(self) -> None:
        self.session.commit()

    def close(self) -> None:
        self.session.close()

    # -- raw evidence (§6/§10: written BEFORE parsing) -----------------------
    def write_raw_evidence(self, kind: str, data: bytes) -> str:
        ref_id = uuid.uuid4().hex
        sha = hashlib.sha256(data).hexdigest()
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        ext = {"html": "html", "json": "json", "pdf": "pdf", "api": "json", "csv": "csv"}.get(
            kind, "bin"
        )
        path = RAW_DIR / f"{ref_id}.{ext}"
        path.write_bytes(data)
        self.session.add(
            RawEvidence(
                ref_id=ref_id,
                kind=kind,
                payload_ref=str(path),
                sha256=sha,
                retrieval_ts=utcnow(),
            )
        )
        self.session.flush()
        return ref_id

    # -- buyer hierarchy (§4.10: walk the chain, never flatten) --------------
    def resolve_buyer(
        self,
        ministry: str | None,
        department: str | None,
        organisation: str | None = None,
        office: str | None = None,
    ) -> int | None:
        node: BuyerOrg | None = None
        parent_id: int | None = None
        for level, name in (
            (BuyerLevel.MINISTRY.value, ministry),
            (BuyerLevel.DEPARTMENT.value, department),
            (BuyerLevel.ORGANISATION.value, organisation),
            (BuyerLevel.OFFICE.value, office),
        ):
            if not name or not name.strip() or name.strip().upper() in {"NA", "N/A"}:
                continue
            name = name.strip()
            node = (
                self.session.query(BuyerOrg)
                .filter(
                    BuyerOrg.level == level, BuyerOrg.name == name, BuyerOrg.parent_id == parent_id
                )
                .first()
            )
            if node is None:
                node = BuyerOrg(level=level, name=name, parent_id=parent_id)
                self.session.add(node)
                self.session.flush()
            parent_id = node.id
        return parent_id

    # -- categories ----------------------------------------------------------
    def get_or_create_category(
        self, category_id: str | None, category_name: str | None
    ) -> int | None:
        if not category_id:
            return None
        cat = self.session.query(Category).filter(Category.category_id == str(category_id)).first()
        if cat is None:
            cat = Category(category_id=str(category_id), category_name=category_name)
            self.session.add(cat)
            self.session.flush()
        return cat.id

    # -- sellers -------------------------------------------------------------
    def get_or_create_seller(
        self, firm_name: str | None, seller_id: str | None = None
    ) -> int | None:
        name = (firm_name or "").strip()
        if not name and not seller_id:
            return None
        seller = None
        if seller_id:
            seller = self.session.query(Seller).filter(Seller.seller_id == str(seller_id)).first()
        if seller is None and name:
            seller = self.session.query(Seller).filter(Seller.firm_name == name).first()
        if seller is None:
            seller = Seller(
                seller_id=str(seller_id) if seller_id else uuid.uuid4().hex, firm_name=name or None
            )
            self.session.add(seller)
            self.session.flush()
        return seller.id

    # -- bids (§4.1/§4.7/§4.9: upsert + append-only change events) -----------
    def upsert_bid(
        self,
        *,
        bid_number: str,
        b_id: str,
        fields: dict,
        fingerprint: str,
        fingerprint_algo_version: str,
        source_url: str,
        raw_ref: str,
    ):
        existing = (
            self.session.query(Bid)
            .filter(or_(Bid.bid_number == bid_number, Bid.b_id == b_id))
            .first()
        )
        if existing is None:
            now = utcnow()
            bid = Bid(
                bid_number=bid_number,
                b_id=b_id,
                fingerprint=fingerprint,
                fingerprint_algo_version=fingerprint_algo_version,
                source_url=source_url,
                raw_ref=raw_ref,
                first_seen=now,
                last_seen=now,
                **fields,
            )
            self.session.add(bid)
            self.session.flush()
            return bid, True, []

        if existing.fingerprint == fingerprint:
            # No change: only refresh last_seen, never overwrite identical data.
            existing.last_seen = utcnow()
            return existing, False, []

        changed: list[str] = []
        prior_ts = existing.retrieval_ts
        for field_name, new_value in fields.items():
            old_value = getattr(existing, field_name, None)
            if _canon(old_value) != _canon(new_value):
                self._append_change("bid", bid_number, field_name, old_value, new_value, prior_ts)
                changed.append(field_name)
                setattr(existing, field_name, new_value)
        existing.fingerprint = fingerprint
        existing.fingerprint_algo_version = fingerprint_algo_version
        existing.retrieval_ts = utcnow()
        existing.last_seen = utcnow()
        self.session.flush()
        return existing, False, changed

    def _append_change(
        self,
        entity_type: str,
        entity_id: str,
        field: str,
        prior: object,
        new: object,
        prior_ts: datetime | None,
    ) -> None:
        self.session.add(
            ChangeEvent(
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                prior_value=None if prior is None else str(_canon(prior)),
                new_value=None if new is None else str(_canon(new)),
                prior_retrieval_ts=prior_ts,
                new_retrieval_ts=utcnow(),
            )
        )

    # -- participation (§4.4: absence = no row, never inferred) --------------
    def record_participation(
        self,
        *,
        bid_id: int,
        seller_id: int,
        stage: str,
        result: str | None = None,
        total_price=None,
        mse_mii_status: str | None = None,
        source_url: str | None = None,
        raw_ref: str | None = None,
    ) -> None:
        row = Participation(
            bid_id=bid_id,
            seller_id=seller_id,
            stage=stage,
            present=True,
            result=result,
            total_price=total_price,
            mse_mii_status=mse_mii_status,
            observed_ts=utcnow(),
            source_url=source_url,
            raw_ref=raw_ref,
        )
        self.session.add(row)

    # -- corrigenda (§4.9: append-only versions, dedup by external id) -------
    def record_corrigendum(
        self,
        *,
        bid_id: int,
        external_id: str | None,
        corrigendum_no: str | None,
        issue_date,
        summary: str | None,
        source_url: str | None,
        raw_ref: str | None,
    ):
        existing = None
        if external_id:
            existing = (
                self.session.query(BidCorrigendum)
                .filter(BidCorrigendum.bid_id == bid_id, BidCorrigendum.external_id == external_id)
                .first()
            )
        if existing is not None:
            return existing, False
        corrigendum = BidCorrigendum(
            bid_id=bid_id,
            external_id=external_id,
            corrigendum_no=corrigendum_no,
            issue_date=issue_date,
            summary=summary,
            source_url=source_url,
            raw_ref=raw_ref,
        )
        self.session.add(corrigendum)
        self.session.flush()
        return corrigendum, True

    # -- documents / line items / links (§8.3-4, §8.17) ----------------------
    def record_document(
        self,
        *,
        bid_id: int | None,
        doc_type: str,
        url: str,
        sha256: str,
        byte_size: int,
        content_type: str | None,
        pdf_signature_valid: bool | None,
        page_count: int | None,
        parse_status: str,
        extracted_text_ref: str | None,
        source_url: str | None,
        raw_ref: str,
    ) -> tuple[BidDocument, bool]:
        existing = (
            self.session.query(BidDocument)
            .filter(BidDocument.bid_id == bid_id, BidDocument.url == url)
            .first()
        )
        if existing is not None:
            return existing, False
        doc = BidDocument(
            bid_id=bid_id,
            doc_type=doc_type,
            url=url,
            sha256=sha256,
            byte_size=byte_size,
            content_type=content_type,
            pdf_signature_valid=pdf_signature_valid,
            page_count=page_count,
            parse_status=parse_status,
            extracted_text_ref=extracted_text_ref,
            source_url=source_url,
            raw_ref=raw_ref,
        )
        self.session.add(doc)
        self.session.flush()
        return doc, True

    def record_document_links(self, document_id: int, links: list[dict]) -> None:
        for link in links:
            self.session.add(
                DocumentLink(
                    document_id=document_id,
                    url=link["url"],
                    anchor_text=link.get("anchor_text"),
                    page_number=link.get("page_number"),
                    context=link.get("context"),
                    extraction_ts=utcnow(),
                )
            )

    def record_line_items(self, document_id: int, items: list[dict]) -> None:
        for it in items:
            self.session.add(
                BidLineItem(
                    document_id=document_id,
                    item_no=it.get("item_no"),
                    description=it.get("description"),
                    quantity=it.get("quantity"),
                    unit=it.get("unit"),
                    unit_price=it.get("unit_price"),
                    total_price=it.get("total_price"),
                    consignee=it.get("consignee"),
                    page_number=it.get("page_number"),
                    confidence=it.get("confidence"),
                )
            )

    # -- awards (§4.2/§8.6: award is separate from L1) ----------------------
    def record_award(
        self,
        *,
        source: str,
        bid_id: int | None,
        l1_seller_id: int | None,
        awarded_value,
        award_date=None,
        status: str = "awarded",
        source_url: str | None = None,
        raw_ref: str | None = None,
    ) -> Award:
        award = Award(
            source=source,
            bid_id=bid_id,
            l1_seller_id=l1_seller_id,
            awarded_value=awarded_value,
            award_date=award_date,
            status=status,
            source_url=source_url,
            raw_ref=raw_ref,
        )
        self.session.add(award)
        self.session.flush()
        return award
