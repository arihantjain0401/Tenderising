"""FastAPI application — the customer HTTP surface.

Thin HTTP layer over the service layer (CLAUDE.md §1). Serves the JSON REST API;
when the React build exists (frontend/dist), it also serves the SPA and falls
back to index.html for client-side routes.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from tenderising.api import gate
from tenderising.api.routers import (
    aggregates,
    ask,
    auth,
    bids,
    chat,
    discovery,
    documents,
    workspace,
)
from tenderising.config import PROJECT_ROOT

app = FastAPI(title="Tenderising API", version="0.1.0")

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(discovery.router)
app.include_router(discovery.export_router)
app.include_router(bids.router)
app.include_router(aggregates.router)
app.include_router(documents.router)
app.include_router(ask.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(workspace.router)
app.include_router(gate.router)


@app.middleware("http")
async def tester_gate(request: Request, call_next):
    path = request.url.path
    if path in gate.PUBLIC_PATHS or gate.is_authed(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return RedirectResponse("/login", status_code=307)


# --- SPA serving (production) ----------------------------------------------
if (FRONTEND_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path.startswith(("api/", "health", "docs", "openapi.json", "redoc")):
            raise HTTPException(status_code=404, detail="not found")
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
