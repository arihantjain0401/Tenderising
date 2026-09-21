"""Embedding via local Ollama (nomic-embed-text)."""

from __future__ import annotations

import json
import urllib.request

from tenderising.config import EMBED_MODEL, OLLAMA_BASE_URL

# Ollama rejects an over-large `/api/embed` request (HTTP 400), so the batch is
# split into bounded groups. The re-index feeds tens of thousands of chunks;
# without batching a single request exceeds Ollama's size/token limit.
_EMBED_BATCH_SIZE = 64


def _embed_batch(batch: list[str]) -> list[list[float]]:
    payload = json.dumps({"model": EMBED_MODEL, "input": batch}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_BASE_URL + "/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("embeddings", [])


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        embeddings.extend(_embed_batch(texts[i : i + _EMBED_BATCH_SIZE]))
    return embeddings


def embed_one(text: str) -> list[float]:
    out = embed_texts([text])
    return out[0] if out else []
