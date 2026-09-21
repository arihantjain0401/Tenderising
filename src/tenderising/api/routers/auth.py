"""Google OAuth sign-in, callback, logout, and the current-user check."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from tenderising.api.auth import google
from tenderising.api.auth import sessions as auth_sessions
from tenderising.api.deps import COOKIE_NAME
from tenderising.db.engine import SessionLocal
from tenderising.db.models import GoogleIdentity, User
from tenderising.service.store import CuratedStoreService

router = APIRouter(prefix="/api/auth", tags=["auth"])

_STATE_COOKIE = "tenderising_oauth_state"
_SESSION_MAX_AGE = 60 * 60 * 24 * 7


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/login")
def login() -> RedirectResponse:
    state = google.new_state()
    resp = RedirectResponse(google.auth_url(state))
    resp.set_cookie(
        _STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, path="/api/auth"
    )
    return resp


@router.get("/callback")
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(status_code=400, detail=f"oauth error: {error}")
    expected = request.cookies.get(_STATE_COOKIE)
    if not expected or not state or state != expected:
        raise HTTPException(status_code=400, detail="invalid oauth state")
    if not code:
        raise HTTPException(status_code=400, detail="missing oauth code")

    token = google.exchange_code(code)
    userinfo = google.fetch_userinfo(token.get("access_token", ""))
    sub = userinfo.get("sub")
    email = userinfo.get("email") or ""
    if not sub:
        raise HTTPException(status_code=400, detail="missing google subject")

    store = CuratedStoreService()
    try:
        user = store.session.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name=userinfo.get("name"), picture_url=userinfo.get("picture"))
            store.session.add(user)
            store.session.flush()
        else:
            user.name = userinfo.get("name") or user.name
            user.picture_url = userinfo.get("picture") or user.picture_url
        user.last_login_at = datetime.now(UTC)

        ident = (
            store.session.query(GoogleIdentity).filter(GoogleIdentity.google_sub == sub).first()
        )
        if ident is None:
            store.session.add(
                GoogleIdentity(
                    user_id=user.id,
                    google_sub=sub,
                    email=email,
                    name=userinfo.get("name"),
                    picture_url=userinfo.get("picture"),
                )
            )
        store.commit()
        user_id = user.id
    finally:
        store.close()

    session_token = auth_sessions.issue(
        user_id, ip=_client_ip(request), user_agent=request.headers.get("user-agent")
    )
    resp = RedirectResponse("/workspace")
    resp.set_cookie(
        COOKIE_NAME, session_token, httponly=True, samesite="lax", max_age=_SESSION_MAX_AGE
    )
    resp.delete_cookie(_STATE_COOKIE, path="/api/auth")
    return resp


@router.post("/logout")
def logout(request: Request) -> JSONResponse:
    auth_sessions.revoke(request.cookies.get(COOKIE_NAME))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@router.get("/me")
def me(request: Request) -> dict:
    user_id = auth_sessions.validate(request.cookies.get(COOKIE_NAME))
    if user_id is None:
        return {"authenticated": False}
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "picture": user.picture_url,
        },
    }
