"""Document-link classification for the links embedded in a bid-document PDF.

The bid-document PDF links to several first-class documents (§8.3): BOQ (CSV/PDF),
GTC, OMP, specs, shared docs. Each is fetched, classified, and indexed.
"""

from __future__ import annotations


def classify_doc_type(url: str) -> str:
    u = url.lower()
    if "boq" in u:
        return "BOQ"
    if "gtc" in u:
        return "GTC"
    if "stc" in u:
        return "STC"
    if "atc" in u:
        return "ATC"
    if "omp" in u:
        return "OMP"
    if "spec" in u:
        return "spec"
    if "category" in u or "categories" in u:
        return "category_list"
    return "document"


def is_document_link(url: str) -> bool:
    """True when the URL points at a fetchable document (PDF/CSV/API doc)."""
    u = url.lower()
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    if u.endswith(".pdf") or u.endswith(".csv"):
        return True
    if "uploaded_documents" in u:
        return True
    if "gtc" in u or "omp" in u or "pdfby" in u:
        return True
    return False
