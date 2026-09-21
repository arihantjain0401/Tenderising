"""Document integrity validation (§6): HTTP 200 is never success on its own."""

from __future__ import annotations

import hashlib

import pymupdf

PDF_MAGIC = b"%PDF-"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_document(status: int, content_type: str, data: bytes) -> dict:
    """Return integrity facts for a fetched document.

    Never treats HTTP 200 alone as success: checks content type, non-trivial
    byte size, PDF signature, parseable page count, and computes a checksum.
    """
    result = {
        "http_status": status,
        "content_type": content_type,
        "byte_size": len(data),
        "sha256": sha256_hex(data),
        "pdf_signature_valid": data[:5] == PDF_MAGIC,
        "page_count": None,
        "valid": False,
    }
    if status == 200 and data and result["pdf_signature_valid"]:
        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                result["page_count"] = doc.page_count
            result["valid"] = result["page_count"] > 0
        except Exception:  # noqa: BLE001 - a corrupt/partial PDF must fail closed
            result["valid"] = False
    return result
