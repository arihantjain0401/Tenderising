"""Tender detail: full header plus tab-scoped sub-resources.

``bid_number`` is a query parameter because GeM bid numbers contain slashes
(e.g. ``GEM/2026/B/7131093``) and therefore cannot be a single path segment.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from tenderising.api import schemas
from tenderising.api.deps import SkillsDep
from tenderising.service.fetch import LiveFetchService
from tenderising.service.skills import Skills

router = APIRouter(prefix="/api/bids", tags=["bids"])


def _detail(bid_number: str, skills: Skills) -> dict:
    d = skills.get_bid_detail(bid_number=bid_number)
    if d is None:
        raise HTTPException(status_code=404, detail="bid not found")
    return d


@router.get("")
def bid_detail(bid_number: str, skills: SkillsDep) -> dict:
    return schemas.public_bid_detail(_detail(bid_number, skills))


@router.get("/documents")
def bid_documents(bid_number: str, skills: SkillsDep) -> dict:
    d = _detail(bid_number, skills)
    return {"documents": [schemas.public_document(x) for x in d.get("documents", [])]}


@router.post("/documents/fetch")
def fetch_documents(bid_number: str, skills: SkillsDep) -> dict:
    """Fetch the bid's documents on demand: serve from DB if already collected,
    else scrape GeM, persist, and return the newly collected documents."""
    detail = _detail(bid_number, skills)
    if detail.get("documents"):
        return {
            "fetched": False,
            "documents": [schemas.public_document(x) for x in detail["documents"]],
        }
    svc = LiveFetchService()
    try:
        bid = svc.fetch_bid(bid_number)
        if bid is None:
            return {"fetched": False, "documents": [], "error": "no live documents found"}
        svc.enrich(bid)
    finally:
        svc.close()
    skills.store.session.expire_all()
    detail = skills.get_bid_detail(bid_number=bid_number) or {}
    return {
        "fetched": True,
        "documents": [schemas.public_document(x) for x in detail.get("documents", [])],
    }


@router.get("/boq")
def bid_boq(bid_number: str, skills: SkillsDep) -> dict:
    d = _detail(bid_number, skills)
    return {"line_items": [schemas.public_line_item(x) for x in d.get("line_items", [])]}


@router.get("/requirements")
def bid_requirements(bid_number: str, skills: SkillsDep) -> dict:
    d = _detail(bid_number, skills)
    return {
        "participation": [schemas.public_participation(x) for x in d.get("participation", [])],
        "award": schemas.public_award(d.get("award")),
    }


@router.get("/corrigenda")
def bid_corrigenda(bid_number: str, skills: SkillsDep) -> dict:
    d = _detail(bid_number, skills)
    return {"corrigenda": [schemas.public_corrigendum(x) for x in d.get("corrigenda", [])]}


@router.get("/history")
def bid_history(bid_number: str, skills: SkillsDep) -> dict:  # noqa: ARG001
    # change_events is append-only and currently empty in practice; return an
    # explicit empty marker so the UI can distinguish "no history" from "unavailable".
    return {"events": []}
