"""Entry gate — a single tester login in front of the whole app.

Mirrors the old stdlib app's gate: everything except /health, /login, /logout
requires a session issued from the tester credentials. Google sign-in for the
Workspace remains "inside" — reachable only after passing this gate.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from tenderising.config import tester_credentials

GATE_COOKIE = "tenderising_gate"
_TTL = 60 * 60 * 24 * 7  # 7 days

_SESSIONS: dict[str, float] = {}
_LOCK = threading.Lock()

PUBLIC_PATHS = {"/health", "/login", "/logout"}


def _issue() -> str:
    token = secrets.token_urlsafe(32)
    with _LOCK:
        _SESSIONS[token] = time.time() + _TTL
    return token


def is_authed(request: Request) -> bool:
    token = request.cookies.get(GATE_COOKIE)
    if not token:
        return False
    with _LOCK:
        expiry = _SESSIONS.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            _SESSIONS.pop(token, None)
            return False
        return True


def _revoke(request: Request) -> None:
    token = request.cookies.get(GATE_COOKIE)
    with _LOCK:
        _SESSIONS.pop(token, None)


_LOGIN_CSS = """
body{font-family:'IBM Plex Sans',system-ui,sans-serif;background:#F8FAFC;color:#0F172A;
  display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
.card{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:32px;width:340px;
  box-shadow:0 1px 3px rgba(0,0,0,.06);}
h1{font-size:20px;margin:0 0 4px;}
.sub{color:#64748B;font-size:14px;margin:0 0 20px;}
label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:#64748B;margin-bottom:14px;}
input{padding:10px 12px;border:1px solid #E2E8F0;border-radius:8px;font-size:15px;}
button{width:100%;padding:11px;background:#1D4ED8;color:#fff;border:none;border-radius:8px;
  font-size:15px;cursor:pointer;margin-top:4px;font-family:inherit;}
button:hover{background:#1E40AF;}
.err{color:#B91C1C;font-size:13px;margin:0 0 12px;}
"""


def _login_page(error: str = "") -> str:
    err = f"<p class='err'>{error}</p>" if error else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Sign in · Tenderising</title><style>{_LOGIN_CSS}</style></head>
<body><div class='card'><h1>Tenderising</h1><p class='sub'>Sign in to continue (tester access)</p>
<form method='post' action='/login'>
<label>Username<input name='username' autocomplete='username'></label>
<label>Password<input name='password' type='password' autocomplete='current-password'></label>
{err}
<button type='submit'>Sign in</button>
</form></div></body></html>"""


router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def login_page() -> HTMLResponse:
    return HTMLResponse(_login_page())


@router.post("/login")
async def login(request: Request):
    raw = (await request.body()).decode("utf-8", "replace")
    fields = urllib.parse.parse_qs(raw)
    username = (fields.get("username") or [""])[0].strip()
    password = (fields.get("password") or [""])[0]
    expect_user, expect_pw = tester_credentials()
    if (
        not expect_pw
        or not hmac.compare_digest(username, expect_user)
        or not hmac.compare_digest(password, expect_pw)
    ):
        return HTMLResponse(_login_page("invalid username or password"), status_code=401)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        GATE_COOKIE, _issue(), httponly=True, samesite="lax", max_age=_TTL, path="/"
    )
    return resp


@router.get("/logout")
def logout(request: Request) -> RedirectResponse:
    _revoke(request)
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(GATE_COOKIE, path="/")
    return resp
