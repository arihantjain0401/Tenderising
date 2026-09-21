"""Chat history — per-Google-user sessions, messages, and widget snapshots.

Google-authed via ``CurrentUser`` (same pattern as the workspace router). The
underlying store is the standalone ``data/chat.db`` (kept out of the curated
procurement DB); sessions are owned by a user id and never cross-leak.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from tenderising.api.deps import CurrentUser
from tenderising.chat import store

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _uid(user: CurrentUser) -> str:
    return str(user.id)


def _owned(session_id: str, user_id: str) -> dict:
    """Return the session if it belongs to the user, else raise 404."""
    session = store.get_session(session_id)
    if session is None or session.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="not found")
    return session


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


@router.get("/sessions")
def list_sessions(user: CurrentUser) -> dict:
    return {"items": store.list_sessions(user_id=_uid(user))}


@router.post("/sessions")
def create_session(user: CurrentUser) -> dict:
    sid = store.create_session(user_id=_uid(user))
    return {"id": sid}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: CurrentUser) -> dict:
    session = _owned(session_id, _uid(user))
    return {
        "id": session["id"],
        "title": session["title"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "widgets": session.get("widgets") or [],
        "messages": store.get_messages(session_id),
    }


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, request: Request, user: CurrentUser) -> dict:
    _owned(session_id, _uid(user))
    body = await _body(request)
    role = (body.get("role") or "").strip()
    content = body.get("content") or ""
    if role not in ("user", "assistant") or not content:
        raise HTTPException(status_code=400, detail="role and content required")
    store.add_message(session_id, role, content)
    return {"ok": True}


@router.put("/sessions/{session_id}/widgets")
async def put_widgets(session_id: str, request: Request, user: CurrentUser) -> dict:
    _owned(session_id, _uid(user))
    body = await _body(request)
    widgets = body.get("widgets")
    if not isinstance(widgets, list):
        raise HTTPException(status_code=400, detail="widgets must be a list")
    store.set_widgets(session_id, widgets)
    return {"ok": True}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, user: CurrentUser) -> dict:
    _owned(session_id, _uid(user))
    store.delete_session(session_id)
    return {"ok": True}
