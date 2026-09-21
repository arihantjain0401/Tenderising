"""Workspace CRUD — all Google-authed, per-user."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from tenderising.api.deps import CurrentUser, SessionDep
from tenderising.service.store import CuratedStoreService
from tenderising.service.workspace import WorkspaceService

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


def get_workspace(user: CurrentUser, session: SessionDep) -> WorkspaceService:
    return WorkspaceService(CuratedStoreService(session), user.id)


WorkspaceDep = Annotated[WorkspaceService, Depends(get_workspace)]


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


@router.get("/saved-tenders")
def list_saved(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_saved_tenders()}


@router.post("/saved-tenders")
async def save_tender(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    bid_number = (body.get("bid_number") or "").strip()
    if not bid_number:
        raise HTTPException(status_code=400, detail="bid_number required")
    return ws.save_tender(bid_number, note=body.get("note"), snapshot=body.get("snapshot"))


@router.delete("/saved-tenders/{item_id}")
def remove_tender(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_tender(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/saved-views")
def list_views(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_saved_views()}


@router.post("/saved-views")
async def create_view(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return ws.save_view(name, filters=body.get("filters"))


@router.put("/saved-views/{item_id}")
async def update_view(item_id: int, request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    if not ws.update_view(item_id, name=body.get("name"), filters=body.get("filters")):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/saved-views/{item_id}")
def remove_view(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_view(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/widgets")
def list_widgets(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_widgets()}


@router.post("/widgets")
async def save_widget(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    kind = (body.get("kind") or "").strip()
    if not kind:
        raise HTTPException(status_code=400, detail="kind required")
    return ws.save_widget(
        kind,
        data=body.get("data"),
        title=body.get("title"),
        session_id=body.get("session_id"),
    )


@router.delete("/widgets/{item_id}")
def remove_widget(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_widget(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/tags")
def list_tags(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_tags()}


@router.get("/notes")
def list_notes(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_notes()}


@router.post("/notes")
async def create_note(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    if not (body.get("body") or "").strip():
        raise HTTPException(status_code=400, detail="body required")
    return ws.create_note(
        body=(body.get("body") or "").strip(),
        title=body.get("title"),
        bid_number=body.get("bid_number"),
        tags=body.get("tags"),
    )


@router.put("/notes/{item_id}")
async def update_note(item_id: int, request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    if not ws.update_note(item_id, body=body.get("body"), title=body.get("title")):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/notes/{item_id}")
def remove_note(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_note(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/alerts")
def list_alerts(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_alerts()}


@router.post("/alerts")
async def create_alert(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    return ws.create_alert(name, filters=body.get("filters"), frequency=body.get("frequency"))


@router.put("/alerts/{item_id}")
async def update_alert(item_id: int, request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    if not ws.update_alert(
        item_id,
        name=body.get("name"),
        filters=body.get("filters"),
        frequency=body.get("frequency"),
        enabled=body.get("enabled"),
    ):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/alerts/{item_id}")
def remove_alert(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_alert(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/pipeline")
def list_pipeline(ws: WorkspaceDep) -> dict:
    return ws.list_pipeline()


@router.post("/pipeline")
async def add_pipeline(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    bid_number = (body.get("bid_number") or "").strip()
    if not bid_number:
        raise HTTPException(status_code=400, detail="bid_number required")
    return ws.add_pipeline(bid_number, stage=body.get("stage") or "new", note=body.get("note"))


@router.patch("/pipeline/{item_id}")
async def move_pipeline(item_id: int, request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    if not ws.move_pipeline(item_id, body.get("stage") or ""):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.delete("/pipeline/{item_id}")
def remove_pipeline(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_pipeline(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/calendar/events")
def list_events(ws: WorkspaceDep) -> dict:
    return {"items": ws.list_events()}


@router.post("/calendar/events")
async def create_event(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    return ws.create_event(
        title,
        starts_at=body.get("starts_at"),
        ends_at=body.get("ends_at"),
        description=body.get("description"),
    )


@router.delete("/calendar/events/{item_id}")
def remove_event(item_id: int, ws: WorkspaceDep) -> dict:
    if not ws.remove_event(item_id):
        raise HTTPException(status_code=404, detail="not found")
    return {"ok": True}


@router.get("/profile")
def get_profile(user: CurrentUser, ws: WorkspaceDep) -> dict:
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "picture": user.picture_url,
        },
        "preferences": ws.get_preferences(),
    }


@router.patch("/preferences")
async def update_preferences(request: Request, ws: WorkspaceDep) -> dict:
    body = await _body(request)
    return ws.update_preferences(
        timezone=body.get("timezone"), default_view=body.get("default_view")
    )
