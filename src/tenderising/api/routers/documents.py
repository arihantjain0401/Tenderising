"""Free document download/export (redirects to the public GeM source)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from tenderising.api.deps import SessionDep
from tenderising.db.models import BidDocument

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/{document_id}/download")
def download(document_id: int, session: SessionDep) -> RedirectResponse:
    doc = session.query(BidDocument).filter(BidDocument.id == document_id).first()
    if doc is None or not doc.url:
        raise HTTPException(status_code=404, detail="document not found")
    return RedirectResponse(url=doc.url)
