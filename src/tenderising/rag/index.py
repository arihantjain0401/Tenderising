"""Build/refresh the RAG vector index from the curated DB + extracted text.

The index is a derived, rebuildable cache in data/rag_index.sqlite — the curated
DB remains the source of truth. Sources: bid_documents extracted text, corrigenda
summaries, and BOQ line-item descriptions.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tenderising.config import DATA_DIR
from tenderising.db.engine import SessionLocal
from tenderising.db.models import BidCorrigendum, BidDocument, BidLineItem
from tenderising.rag.embed import embed_texts

INDEX_PATH = DATA_DIR / "rag_index.sqlite"
CHUNK_SIZE = 1500
OVERLAP = 200


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + size])
        start += size - overlap
    return chunks


def _iter_chunks(session):
    # 1. document extracted text
    for doc in session.query(BidDocument).filter(BidDocument.extracted_text_ref.isnot(None)).all():
        p = Path(doc.extracted_text_ref)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, chunk in enumerate(chunk_text(text)):
            yield {
                "document_id": doc.id,
                "bid_id": doc.bid_id,
                "kind": f"document:{doc.doc_type}",
                "chunk_no": i,
                "text": chunk,
            }
    # 2. corrigenda summaries
    for c in session.query(BidCorrigendum).filter(BidCorrigendum.summary.isnot(None)).all():
        yield {
            "document_id": None,
            "bid_id": c.bid_id,
            "kind": "corrigendum",
            "chunk_no": 0,
            "text": c.summary,
        }
    # 3. BOQ line items
    for li in session.query(BidLineItem).filter(BidLineItem.description.isnot(None)).all():
        if li.description.strip():
            yield {
                "document_id": li.document_id,
                "bid_id": None,
                "kind": "line_item",
                "chunk_no": 0,
                "text": f"{li.description} · qty {li.quantity} {li.unit or ''} · {li.consignee or ''}",
            }


def refresh() -> dict:
    session = SessionLocal()
    try:
        chunks = list(_iter_chunks(session))
    finally:
        session.close()

    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(INDEX_PATH)
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "id INTEGER PRIMARY KEY, document_id INTEGER, bid_id INTEGER, "
            "kind TEXT, chunk_no INTEGER, text TEXT, embedding TEXT)"
        )
        con.execute("DELETE FROM chunks")

        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts) if texts else []
        rows = []
        for c, emb in zip(chunks, embeddings, strict=False):
            rows.append(
                (
                    c["document_id"],
                    c["bid_id"],
                    c["kind"],
                    c["chunk_no"],
                    c["text"],
                    json.dumps(emb),
                )
            )
        con.executemany(
            "INSERT INTO chunks (document_id, bid_id, kind, chunk_no, text, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.commit()
        return {"chunks": len(rows), "embedded": len(embeddings)}
    finally:
        con.close()
