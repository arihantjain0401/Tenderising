"""Cosine top-k search over the RAG index."""

from __future__ import annotations

import json
import math
import sqlite3

from tenderising.config import RAG_TOP_K
from tenderising.rag.embed import embed_one
from tenderising.rag.index import INDEX_PATH


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search(query: str, top_k: int = RAG_TOP_K) -> list[dict]:
    qv = embed_one(query)
    if not qv:
        return []
    con = sqlite3.connect(INDEX_PATH)
    try:
        rows = con.execute(
            "SELECT id, document_id, bid_id, kind, chunk_no, text, embedding FROM chunks"
        ).fetchall()
    finally:
        con.close()

    scored = []
    for cid, document_id, bid_id, kind, chunk_no, text, emb in rows:
        if not emb:
            continue
        vec = json.loads(emb)
        scored.append(
            {
                "id": cid,
                "document_id": document_id,
                "bid_id": bid_id,
                "kind": kind,
                "chunk_no": chunk_no,
                "text": text[:1200],
                "score": round(_cosine(qv, vec), 4),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
