"""Bid document collector: showbidDocument/<b_id> -> validated PDF -> typed fields.

Raw evidence is written before parsing; integrity is validated (§6); text is
retained for fallback; links are extracted and every linked document (BOQ, GTC,
OMP, specs, …) is fetched, classified and indexed as a first-class bid_document
(§8.3). A linked GeM BoqLineItemsDocument CSV is parsed into bid_line_items.
"""

from __future__ import annotations

from tenderising.config import SHOWBID_DOCUMENT, ParseStatus
from tenderising.db.models import Bid, BidDocument
from tenderising.extract.boq import parse_boq_csv
from tenderising.extract.checks import sha256_hex, validate_document
from tenderising.extract.documents import classify_doc_type, is_document_link
from tenderising.extract.pdf import extract_line_items, extract_links, extract_text
from tenderising.service.store import RAW_DIR, CuratedStoreService

_PDF_MAGIC = b"%PDF-"


class DocumentCollector:
    def __init__(self, session, store: CuratedStoreService):
        self.session = session
        self.store = store

    def collect(self, bid: Bid, doc_type: str = "bid_document") -> BidDocument | None:
        url = SHOWBID_DOCUMENT + bid.b_id
        status, content_type, data = self.session.get(url)
        # Empty body = no document for this bid (missing, distinct from failed).
        if status != 200 or not data:
            return None

        raw_ref = self.store.write_raw_evidence("pdf", data)
        check = validate_document(status, content_type, data)
        parse_status = ParseStatus.PARSED.value if check["valid"] else ParseStatus.FAILED.value

        extracted_text_ref = None
        if check["valid"]:
            text = extract_text(data)
            if text:
                text_path = RAW_DIR / f"{raw_ref}.txt"
                text_path.write_text(text, encoding="utf-8")
                extracted_text_ref = str(text_path)

        doc, created = self.store.record_document(
            bid_id=bid.id,
            doc_type=doc_type,
            url=url,
            sha256=check["sha256"],
            byte_size=check["byte_size"],
            content_type=content_type,
            pdf_signature_valid=check["pdf_signature_valid"],
            page_count=check["page_count"],
            parse_status=parse_status,
            extracted_text_ref=extracted_text_ref,
            source_url=url,
            raw_ref=raw_ref,
        )

        # Only parse + index linked documents the first time this document is seen.
        if created and check["valid"]:
            links = extract_links(data)
            self.store.record_document_links(doc.id, links)
            self.store.record_line_items(doc.id, extract_line_items(data))
            self._collect_linked_documents(bid, links)
        return doc

    def _collect_linked_documents(self, bid: Bid, links: list[dict]) -> list[BidDocument]:
        collected: list[BidDocument] = []
        for link in links:
            url = link["url"]
            if not is_document_link(url):
                continue
            status, content_type, data = self.session.get(url)
            if status != 200 or not data:
                continue
            doc_type = classify_doc_type(url)
            is_pdf = data[:5] == _PDF_MAGIC
            is_csv = url.lower().endswith(".csv")
            kind = "pdf" if is_pdf else ("csv" if is_csv else "html")
            raw_ref = self.store.write_raw_evidence(kind, data)

            check = validate_document(status, content_type, data) if is_pdf else None
            doc, created = self.store.record_document(
                bid_id=bid.id,
                doc_type=doc_type,
                url=url,
                sha256=sha256_hex(data),
                byte_size=len(data),
                content_type=content_type,
                pdf_signature_valid=check["pdf_signature_valid"] if check else None,
                page_count=check["page_count"] if check else None,
                parse_status=ParseStatus.PARSED.value,
                extracted_text_ref=None,
                source_url=url,
                raw_ref=raw_ref,
            )
            if not created:
                collected.append(doc)
                continue

            if is_csv and doc_type == "BOQ":
                self.store.record_line_items(doc.id, parse_boq_csv(data.decode("utf-8", "replace")))
            elif is_pdf and check and check["valid"]:
                text = extract_text(data)
                if text:
                    text_path = RAW_DIR / f"{raw_ref}.txt"
                    text_path.write_text(text, encoding="utf-8")
                    doc.extracted_text_ref = str(text_path)
                self.store.record_document_links(doc.id, extract_links(data))
                if doc_type == "BOQ":
                    self.store.record_line_items(doc.id, extract_line_items(data))
            collected.append(doc)
        return collected
