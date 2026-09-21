# Tenderising UX revamp — status & runbook

Rebuild the customer surface around two product areas (**Ask Tenderising** and **Discovery**) plus a
private **Workspace** and a decision-oriented **Tender detail**. Decisions locked 2026-09-20:

1. **Frontend: React + Vite + TypeScript**, backend **FastAPI** (thin layer over the existing
   `service`/`chat`/`mcp` code). Replaces the stdlib `http.server` surface in `src/tenderising/web/app.py`.
2. **Workspace: full Google OAuth2** (server-side sessions, per-user tables).
3. **Discovery filters: backable fields only** — value/EMD/state/city are "not available yet".

## Public API (FastAPI, `src/tenderising/api/`)

- `GET /health`
- `GET /api/search/bids` — filtered/sorted/paginated; `GET /api/search/facets`; `GET /api/export/bids` (CSV)
- `GET /api/bids?bid_number=…` + `/documents` `/boq` `/requirements` `/corrigenda` `/history`
  (bid_number is a **query param** — GeM bid numbers contain slashes)
- `GET /api/aggregates/{status,departments,categories,deadlines,activity,summary}`
- `GET /api/documents/{id}/download` (302 → GeM source)
- (planned) `POST /api/ask/stream` SSE, `POST /api/ask`; `GET/POST /api/auth/*`; `/api/workspace/*`

Sanitization lives in `src/tenderising/api/schemas.py` — the single choke-point that strips internal
ids/raw status/fingerprints/timestamps before anything leaves the API.

## Run (dev, two terminals)

```sh
# terminal 1 — backend
uv run uvicorn tenderising.api.main:app --reload --port 8000
# terminal 2 — frontend (proxies /api → :8000)
cd frontend && npm run dev
```

Build check: `cd frontend && npm run typecheck && npm run build`. Backend lint/tests: `uv run ruff
check src && uv run pytest -q`.

## Google OAuth setup (Phase 5)

1. Google Cloud Console → project → **APIs & Services → OAuth consent screen** (external or internal;
   add scopes `openid email profile`).
2. **Credentials → Create credentials → OAuth client ID → Web application**.
3. Authorized redirect URI:
   - dev: `http://localhost:5173/api/auth/callback` (Vite proxies `/api` → backend)
   - prod: `https://<ngrok-or-cloudflared-host>/api/auth/callback`
4. Create `credentials/google.env` (gitignored — never commit):
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=http://localhost:5173/api/auth/callback
   ```

## Phase status

- [x] **0** deps + FastAPI scaffold
- [x] **1** read-only API (search/facets/export/detail/tabs/aggregates/documents) + `Skills` extensions
- [x] **2** frontend shell + design system + Discovery page
- [x] **3** Tender detail (tabs)
- [x] **4** Ask (SSE chat + deterministic collage planner)
- [x] **5** Google OAuth + Workspace backend + migration (live sign-in untested until consent screen is configured)
- [x] **6** Workspace UI (sign-in, saved tenders, notes/tags, alerts, pipeline, profile, premium CTA)
- [x] **7** Discovery↔Ask context handoff + polish
- [x] **8** prod serving (SPA from uvicorn on :8070 via cloudflared) — legacy stdlib `web/app.py` retired (file kept for rollback)

## Production

- `https://tenderising.com` (Cloudflare tunnel → `localhost:8070`) now serves the new FastAPI + React app.
- **Entry gate:** a tester login (`tester` / `@123Tender`, in gitignored `credentials/tester.env`) sits in
  front of the whole app — `api/gate.py` middleware blocks everything except `/health`, `/login`,
  `/logout`. Google sign-in remains "inside" (Workspace only).
- The web launchd job (`com.tenderising.web`) runs `python -m uvicorn tenderising.api.main:app --port 8070`
  with `GOOGLE_REDIRECT_URI=https://tenderising.com/api/auth/callback`.
- Cutover: edit `deploy/launchd/com.tenderising.web.plist`, copy to `~/Library/LaunchAgents/`,
  `launchctl kickstart -k gui/$(id -u)/com.tenderising.web`. Build the SPA first: `cd frontend && npm run build`.
