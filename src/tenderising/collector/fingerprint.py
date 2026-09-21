"""Bid fingerprint (§9): sha256 over canonically-sorted fields + document hashes.

A change in fingerprint on a known bid_number signals a new version/corrigendum —
never a silent overwrite. fingerprint_algo_version is stored so the algorithm can
evolve.
"""

from __future__ import annotations

import hashlib
import json

from tenderising.config import FINGERPRINT_ALGO_VERSION


def bid_fingerprint(fields: dict, document_sha256s: list[str] | None = None) -> str:
    """Compute the fp_v1 fingerprint for a bid.

    `fields` is the normalised dict of changeable columns (json-serialisable;
    datetimes become ISO strings via default=str). `document_sha256s` are the
    sorted hashes of the bid's documents (empty at listing stage).
    """
    docs = sorted(d for d in (document_sha256s or []) if d)
    payload = {
        "algo": FINGERPRINT_ALGO_VERSION,
        "fields": fields,
        "documents": docs,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
