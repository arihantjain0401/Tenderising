"""Read-only "index of bids" web server over the curated DB.

Stdlib-only (http.server). Serves:
  GET /                    -> paginated index of bids (like a show/serials index)
  GET /bid/<bid_number>    -> one bid's detail (buyer, corrigenda, documents,
                              line items, participation, award)
  GET /stats               -> DB summary
  GET /health              -> {"ok": true}

Reads the DB directly (read-only) — no writes, no credentials.
"""

from __future__ import annotations

import hmac
import html
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sqlalchemy import func

from tenderising.chat import agent as chat_agent
from tenderising.chat import store as chat_store
from tenderising.chat.providers import list_models, make_provider
from tenderising.config import BID_STATUS_ACTIVE, PROJECT_ROOT
from tenderising.db.engine import SessionLocal
from tenderising.db.models import (
    Award,
    Bid,
    BidCorrigendum,
    BidDocument,
    BidLineItem,
    BuyerOrg,
    Participation,
    Seller,
)
from tenderising.mcp import server as mcp_server
from tenderising.mcp.tools import build_registry

PER_PAGE = 50
PORT = 8070

_SRC_ROOT = Path(__file__).resolve().parent.parent  # .../src/tenderising

_REGISTRY = build_registry()

# --- auth (in-memory session tokens; single admin account) -----------------
_SESSIONS: dict[str, float] = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL = 60 * 60 * 24 * 7  # 7 days
_COOKIE_NAME = "tenderising_session"

# Paths that require a signed-in session. Everything else (/, /bid/*, /stats,
# /health) stays public read-only over already-public GeM data.
_GATED_PREFIXES = ("/chatlocal", "/mcp")


def _admin_credentials() -> tuple[str, str]:
    """Admin username/password from the environment, else credentials/admin.env.

    Never hardcoded here: the file is gitignored, mirroring credentials/deepseek.env.
    """
    user = os.environ.get("TENDERISING_ADMIN_USER", "").strip()
    pw = os.environ.get("TENDERISING_ADMIN_PASS", "")
    env_file = PROJECT_ROOT / "credentials" / "admin.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TENDERISING_ADMIN_USER=") and not user:
                user = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("TENDERISING_ADMIN_PASS=") and not pw:
                pw = line.split("=", 1)[1].strip().strip('"').strip("'")
    return (user or "admin"), pw


def _issue_session() -> str:
    token = secrets.token_urlsafe(32)
    with _SESSIONS_LOCK:
        _SESSIONS[token] = time.time() + _SESSION_TTL
    return token


def _validate_session(token: str) -> bool:
    if not token:
        return False
    with _SESSIONS_LOCK:
        expiry = _SESSIONS.get(token)
        if expiry is None:
            return False
        if time.time() > expiry:
            _SESSIONS.pop(token, None)
            return False
        return True


def _drop_session(token: str) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token, None)


_LOGIN_CSS = """
.login-card{max-width:340px;margin:40px auto;background:#fff;border-radius:8px;
  padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.08);}
.login-card form{display:flex;flex-direction:column;gap:14px;}
.login-card label{font-size:13px;color:#666;display:flex;flex-direction:column;gap:6px;}
.login-card input{padding:10px;font-size:15px;border:1px solid #d6dbe1;border-radius:8px;}
.login-card button{padding:11px;background:#0f5e8b;color:#fff;border:none;border-radius:8px;
  font-size:15px;cursor:pointer;}
.login-err{color:#b00020;font-size:13px;margin:0;}
"""


def _login_page(error: str = "") -> str:
    err = f"<p class='login-err'>{_esc(error)}</p>" if error else ""
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Sign in · GeM intelligence</title><style>{_CSS}{_LOGIN_CSS}</style></head><body>
<header><h1>GeM intelligence</h1><p>sign in to continue</p></header>
<main><div class='login-card'>
<form method='post' action='/login'>
<label>Username<input name='username' autocomplete='username' value='admin'></label>
<label>Password<input name='password' type='password' autocomplete='current-password'></label>
{err}
<button type='submit'>Sign in</button>
</form>
</div></main></body></html>"""


_CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;
  background:#f5f6f8;color:#1a1a1a;}
header{background:#0f5e8b;color:#fff;padding:16px 24px;}
header h1{margin:0;font-size:20px;font-weight:600;}
header p{margin:4px 0 0;font-size:13px;opacity:.85;}
main{max-width:1080px;margin:24px auto;padding:0 16px;}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;
  overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #e6e8eb;font-size:14px;}
th{background:#eef2f6;font-weight:600;color:#333;}
tr:hover td{background:#f7fafc;}
a{color:#0f5e8b;text-decoration:none;} a:hover{text-decoration:underline;}
.pager{margin:16px 0;display:flex;gap:12px;align-items:center;font-size:14px;}
.muted{color:#888;}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;
  background:#e8f0fe;color:#0f5e8b;}
.card{background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.08);
  margin-bottom:16px;}
.kv{display:grid;grid-template-columns:180px 1fr;gap:6px 12px;font-size:14px;}
.kv dt{color:#666;} .kv dd{margin:0;}
h2{font-size:16px;margin:0 0 12px;}
h3{font-size:14px;margin:20px 0 8px;color:#0f5e8b;}
small{color:#999;}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch;}
@media (max-width:720px){
  header{padding:12px 16px;}
  header h1{font-size:17px;}
  header p{font-size:12px;}
  main{margin:12px auto;padding:0 12px;}
  th,td{padding:8px 9px;font-size:13px;}
  .kv{grid-template-columns:1fr;}
  .card{padding:14px;}
  .pager{flex-wrap:wrap;}
}
"""


def _esc(value) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def _dt(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _org_chain(session, office_id):
    names = []
    node = session.query(BuyerOrg).filter(BuyerOrg.id == office_id).first() if office_id else None
    while node is not None:
        names.append(f"{node.level}: {node.name}")
        node = (
            session.query(BuyerOrg).filter(BuyerOrg.id == node.parent_id).first()
            if node.parent_id
            else None
        )
    return " → ".join(reversed(names)) if names else ""


def _index_page(page: int) -> str:
    session = SessionLocal()
    try:
        total = session.query(func.count(Bid.id)).scalar()
        bids = (
            session.query(Bid)
            .order_by(Bid.end_date.is_(None), Bid.end_date.asc(), Bid.id.desc())
            .offset((page - 1) * PER_PAGE)
            .limit(PER_PAGE)
            .all()
        )
        rows = []
        for b in bids:
            rows.append(
                f"<tr><td><a href='/bid/{_esc(b.bid_number)}'>{_esc(b.bid_number)}</a></td>"
                f"<td>{_esc(b.category_name)}</td>"
                f"<td>{_esc(_org_chain(session, b.office_id))}</td>"
                f"<td>{_dt(b.end_date)}</td>"
                f"<td>{_esc(b.status_normalized or b.status_raw)}</td>"
                f"<td>{_esc(b.total_quantity)}</td></tr>"
            )
        pages = (total + PER_PAGE - 1) // PER_PAGE
        pager = ""
        if page > 1:
            pager += f"<a href='/index?page={page - 1}'>← prev</a>"
        pager += f"<span class='muted'>page {page} / {max(pages, 1)} · {total} bids</span>"
        if page < pages:
            pager += f"<a href='/index?page={page + 1}'>next →</a>"
        return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>GeM bids index</title><style>{_CSS}</style></head><body>
<header><h1>GeM bids index</h1><p><a href='/' style='color:#fff'>← chat</a></p></header>
<main>
<div class='pager'><a href='/stats'>stats</a> {pager}</div>
<div class='tablewrap'><table><thead><tr><th>Bid number</th><th>Item / category</th><th>Buyer</th>
<th>End date (UTC)</th><th>Status</th><th>Qty</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<div class='pager'>{pager}</div>
</main></body></html>"""
    finally:
        session.close()


def _detail_page(bid_number: str) -> str:
    session = SessionLocal()
    try:
        b = session.query(Bid).filter(Bid.bid_number == bid_number).first()
        if b is None:
            return f"<h1>Not found</h1><p>{_esc(bid_number)}</p>"

        flags = " ".join(
            tag
            for tag, flag in [
                ("high-value", b.is_high_value),
                ("bunch", b.is_bunch),
                ("custom", b.is_custom_item),
                ("global", b.global_tendering),
                ("single-packet", b.single_packet),
            ]
            if flag
        )

        corrigenda = session.query(BidCorrigendum).filter(BidCorrigendum.bid_id == b.id).all()
        documents = session.query(BidDocument).filter(BidDocument.bid_id == b.id).all()
        line_items = (
            session.query(BidLineItem)
            .join(BidDocument, BidLineItem.document_id == BidDocument.id)
            .filter(BidDocument.bid_id == b.id)
            .all()
        )
        participation = (
            session.query(Participation, Seller.firm_name)
            .join(Seller, Participation.seller_id == Seller.id)
            .filter(Participation.bid_id == b.id)
            .all()
        )
        award = session.query(Award).filter(Award.bid_id == b.id).first()

        corr_rows = (
            "".join(
                f"<tr><td>{_esc(c.corrigendum_no)}</td><td>{_dt(c.issue_date)}</td>"
                f"<td>{_esc((c.summary or '')[:160])}</td></tr>"
                for c in corrigenda
            )
            or "<tr><td colspan='3' class='muted'>none</td></tr>"
        )

        doc_rows = (
            "".join(
                f"<tr><td>{_esc(d.doc_type)}</td><td>{_esc(d.page_count or '')}</td>"
                f"<td>{_esc(d.byte_size or '')}</td><td class='muted'>{_esc((d.url or '')[:70])}</td></tr>"
                for d in documents
            )
            or "<tr><td colspan='4' class='muted'>none</td></tr>"
        )

        li_rows = (
            "".join(
                f"<tr><td>{_esc(it.item_no)}</td><td>{_esc(it.description)}</td>"
                f"<td>{_esc(it.quantity)}</td><td>{_esc(it.unit)}</td>"
                f"<td>{_esc(it.consignee)}</td></tr>"
                for it in line_items
            )
            or "<tr><td colspan='5' class='muted'>none</td></tr>"
        )

        part_rows = (
            "".join(
                f"<tr><td>{_esc(p.stage)}</td><td>{_esc(firm_name)}</td>"
                f"<td>{_esc(p.result)}</td><td>{_esc(p.total_price)}</td></tr>"
                for p, firm_name in participation
            )
            or "<tr><td colspan='4' class='muted'>none</td></tr>"
        )

        award_html = (
            f"<p>source={_esc(award.source)} · L1 seller id={_esc(award.l1_seller_id)} · "
            f"value={_esc(award.awarded_value)}</p>"
            if award
            else "<p class='muted'>none</p>"
        )

        return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{_esc(b.bid_number)}</title><style>{_CSS}</style></head><body>
<header><h1>{_esc(b.bid_number)}</h1><p><a href='/index' style='color:#fff'>← index</a></p></header>
<main>
<div class='card'>
<h2>Bid</h2>
<dl class='kv'>
<dt>Status</dt><dd>{_esc(b.status_normalized or b.status_raw)} <span class='muted'>(raw: {_esc(b.status_raw)})</span></dd>
<dt>Internal id</dt><dd>{_esc(b.b_id)}</dd>
<dt>Buyer</dt><dd>{_esc(_org_chain(session, b.office_id))}</dd>
<dt>Start / end</dt><dd>{_dt(b.start_date)} → {_dt(b.end_date)} <span class='muted'>(UTC)</span></dd>
<dt>Category</dt><dd>{_esc(b.category_name)}</dd>
<dt>Quantity</dt><dd>{_esc(b.total_quantity)}</dd>
<dt>Flags</dt><dd>{flags or '<span class="muted">—</span>'}</dd>
<dt>First / last seen</dt><dd>{_dt(b.first_seen)} / {_dt(b.last_seen)}</dd>
</dl>
</div>
<div class='card'><h2>Award</h2>{award_html}</div>
<div class='card'><h3>Corrigenda</h3>
<div class='tablewrap'><table><thead><tr><th>No.</th><th>Issued</th><th>Summary</th></tr></thead><tbody>{corr_rows}</tbody></table></div></div>
<div class='card'><h3>Documents</h3>
<div class='tablewrap'><table><thead><tr><th>Type</th><th>Pages</th><th>Bytes</th><th>URL</th></tr></thead><tbody>{doc_rows}</tbody></table></div></div>
<div class='card'><h3>Line items (BOQ)</h3>
<div class='tablewrap'><table><thead><tr><th>#</th><th>Description</th><th>Qty</th><th>Unit</th><th>Consignee</th></tr></thead><tbody>{li_rows}</tbody></table></div></div>
<div class='card'><h3>Participation</h3>
<div class='tablewrap'><table><thead><tr><th>Stage</th><th>Seller</th><th>Result</th><th>Price</th></tr></thead><tbody>{part_rows}</tbody></table></div></div>
</main></body></html>"""
    finally:
        session.close()


def _stats_page() -> str:
    session = SessionLocal()
    try:
        total = session.query(func.count(Bid.id)).scalar()
        active = (
            session.query(func.count(Bid.id)).filter(Bid.b_status_raw == BID_STATUS_ACTIVE).scalar()
        )
        docs = session.query(func.count(BidDocument.id)).scalar()
        items = session.query(func.count(BidLineItem.id)).scalar()
        sellers = session.query(func.count(Seller.id)).scalar()
        awards = session.query(func.count(Award.id)).scalar()
        return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>stats</title><style>{_CSS}</style></head><body>
<header><h1>Stats</h1><p><a href='/index' style='color:#fff'>← index</a></p></header>
<main><div class='card'><dl class='kv'>
<dt>Bids</dt><dd>{total}</dd><dt>Active</dt><dd>{active}</dd>
<dt>Documents</dt><dd>{docs}</dd><dt>Line items</dt><dd>{items}</dd>
<dt>Sellers</dt><dd>{sellers}</dd><dt>Awards</dt><dd>{awards}</dd>
</dl></div></main></body></html>"""
    finally:
        session.close()


_CHAT_CSS = """
html,body{height:100%;margin:0;overscroll-behavior:none;}
.chat-shell{display:flex;height:100vh;height:100dvh;height:calc(var(--vh,1vh)*100);overflow:hidden;}
.sidebar{width:260px;min-width:260px;background:#0f2d45;color:#fff;
  display:flex;flex-direction:column;overflow-y:auto;}
.sidebar-head{padding:12px;border-bottom:1px solid rgba(255,255,255,.12);}
.sidebar-head a{color:#9cc7e8;}
#new{width:100%;padding:8px;background:#1d8f6a;color:#fff;border:none;border-radius:6px;
  cursor:pointer;font-size:14px;}
#sessions{padding:8px;}
.sess{display:flex;align-items:center;justify-content:space-between;gap:6px;
  padding:8px 10px;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:2px;}
.sess:hover{background:rgba(255,255,255,.08);}
.sess.active{background:rgba(255,255,255,.16);}
.sess-title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;}
.sess-del{background:none;border:none;color:rgba(255,255,255,.45);cursor:pointer;
  font-size:16px;line-height:1;}
.sess-del:hover{color:#fff;}
.chat-main{flex:1;display:flex;flex-direction:column;background:#f5f6f8;min-width:0;min-height:0;}
.chat-top{padding:10px 16px;background:#fff;border-bottom:1px solid #e6e8eb;
  display:flex;align-items:center;gap:8px;font-size:14px;flex-shrink:0;}
.chat-top a{color:#0f5e8b;}
#thread{flex:1;overflow-y:auto;padding:20px 16px;min-height:0;
  -webkit-overflow-scrolling:touch;overscroll-behavior:contain;}
.msg{display:flex;margin-bottom:14px;}
.msg.user{justify-content:flex-end;}
.bubble{max-width:72%;padding:10px 14px;border-radius:14px;font-size:15px;
  line-height:1.5;background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.08);}
.msg.user .bubble{background:#0f5e8b;color:#fff;}
.body{white-space:pre-wrap;word-wrap:break-word;}
.body p{margin:0 0 8px;}
.body table{border-collapse:collapse;margin:8px 0;font-size:13px;width:100%;}
.body th,.body td{border:1px solid #d6dbe1;padding:5px 8px;text-align:left;}
.body th{background:#eef2f6;font-weight:600;}
.body code{background:#f0f2f5;padding:1px 5px;border-radius:3px;font-size:13px;
  font-family:ui-monospace,Menlo,monospace;}
.body pre{background:#f0f2f5;padding:10px;border-radius:6px;overflow-x:auto;font-size:13px;}
.body pre code{background:none;padding:0;}
.body ul,.body ol{margin:4px 0 8px;padding-left:20px;}
.body blockquote{border-left:3px solid #cfd6de;margin:8px 0;padding-left:10px;color:#666;}
.body a{color:#0f5e8b;}
.think{margin-bottom:8px;font-size:13px;color:#7a7f86;}
.think-head{cursor:pointer;user-select:none;font-weight:600;}
.think-body{margin-top:4px;background:#f0f2f5;border-left:3px solid #cfd6de;padding:8px;
  border-radius:4px;white-space:pre-wrap;color:#666;font-size:12px;}
.chips{font-size:12px;color:#0f5e8b;margin-top:8px;}
.msg.user .chips{color:#cfe6f7;}
.composer{display:flex;gap:8px;padding:12px 16px calc(12px + env(safe-area-inset-bottom));
  background:#fff;border-top:1px solid #e6e8eb;flex-shrink:0;}
.composer textarea{flex:1;font-size:16px;padding:10px;border:1px solid #d6dbe1;
  border-radius:8px;resize:none;box-sizing:border-box;min-height:44px;}
.composer button{padding:0 22px;background:#0f5e8b;color:#fff;border:none;border-radius:8px;
  font-size:15px;cursor:pointer;min-height:44px;}
.composer button:disabled{opacity:.5;cursor:default;}
#menu{display:none;background:#fff;border:1px solid #d6dbe1;border-radius:6px;
  font-size:16px;line-height:1;padding:5px 9px;cursor:pointer;}
@media (max-width:720px){
  .sidebar{position:absolute;left:0;top:0;bottom:0;z-index:20;width:240px;min-width:0;
    transform:translateX(-100%);transition:transform .18s ease;box-shadow:0 0 24px rgba(0,0,0,.35);}
  .sidebar.open{transform:translateX(0);}
  .chat-main{width:100%;}
  .bubble{max-width:92%;}
  .composer button{padding:0 14px;}
  .chat-top{flex-wrap:wrap;}
  #menu{display:inline-block;}
  .body table{display:block;overflow-x:auto;white-space:nowrap;}
}
"""

_CHAT_JS = """
(function(){function fv(){document.documentElement.style.setProperty('--vh',(window.innerHeight*0.01)+'px');}fv();window.addEventListener('resize',fv);window.addEventListener('orientationchange',fv);})();
const go=document.getElementById('go'),q=document.getElementById('q'),
sel=document.getElementById('model'),ms=document.getElementById('mstatus'),
thread=document.getElementById('thread');
let currentSession=null;
const side=document.querySelector('.sidebar'),menu=document.getElementById('menu');
function closeSide(){if(side)side.classList.remove('open');}
if(menu)menu.onclick=()=>{if(side)side.classList.toggle('open');};
function scrollBottom(){thread.scrollTop=thread.scrollHeight;}
async function loadModels(){try{const r=await fetch('/chatlocal/models');
const models=await r.json();sel.innerHTML='';
for(const m of models){const o=document.createElement('option');
o.value=m.provider+'|'+m.model;
o.textContent=(m.provider==='deepseek'?'☁ ':'💻 ')+m.model;sel.appendChild(o);}
if(models.length)ms.textContent='';}catch(e){ms.textContent='(models unavailable)';}}
function toolNames(rounds){return (rounds||[]).map(t=>typeof t==='string'?t:(t.tool||t.name||'')).filter(Boolean).join(', ');}
function renderMd(el,text){if(window.marked&&window.DOMPurify){el.innerHTML=DOMPurify.sanitize(marked.parse(text||''));}else{el.textContent=text||'';}}
function renderMessage(role,content,rounds){
const row=document.createElement('div');row.className='msg '+(role==='user'?'user':'assistant');
const b=document.createElement('div');b.className='bubble';
const body=document.createElement('div');body.className='body';
if(role==='assistant'){renderMd(body,content);}else{body.textContent=content||'';}
b.appendChild(body);
if(rounds&&rounds.length){const c=document.createElement('div');c.className='chips';
c.textContent='used: '+toolNames(rounds);b.appendChild(c);}
row.appendChild(b);thread.appendChild(row);scrollBottom();}
async function refreshSessions(){const r=await fetch('/chatlocal/sessions');
const sessions=await r.json();const el=document.getElementById('sessions');el.innerHTML='';
for(const s of sessions){const d=document.createElement('div');
d.className='sess'+(s.id===currentSession?' active':'');
d.onclick=()=>loadSession(s.id);
const t=document.createElement('span');t.className='sess-title';
t.textContent=s.title||'(untitled)';
const del=document.createElement('button');del.className='sess-del';del.textContent='×';
del.title='Delete';del.onclick=e=>{e.stopPropagation();deleteSession(s.id);};
d.appendChild(t);d.appendChild(del);el.appendChild(d);}}
async function newSession(){const r=await fetch('/chatlocal/sessions',{method:'POST'});
const d=await r.json();currentSession=d.session_id;thread.innerHTML='';refreshSessions();closeSide();}
async function loadSession(id){currentSession=id;closeSide();
const r=await fetch('/chatlocal/sessions/'+id);const d=await r.json();
thread.innerHTML='';for(const m of(d.messages||[]))renderMessage(m.role,m.content,m.tool_rounds);
refreshSessions();}
async function deleteSession(id){await fetch('/chatlocal/sessions/'+id,{method:'DELETE'});
if(currentSession===id){currentSession=null;thread.innerHTML='';}refreshSessions();}
function newAssistantBubble(){
const row=document.createElement('div');row.className='msg assistant';
const b=document.createElement('div');b.className='bubble';
const think=document.createElement('div');think.className='think';think.style.display='none';
const th=document.createElement('div');th.className='think-head';th.textContent='Thinking';
const tb=document.createElement('div');tb.className='think-body';
think.appendChild(th);think.appendChild(tb);
th.onclick=()=>{tb.style.display=tb.style.display==='none'?'block':'none';};
const body=document.createElement('div');body.className='body';
const chips=document.createElement('div');chips.className='chips';
b.appendChild(think);b.appendChild(body);b.appendChild(chips);
row.appendChild(b);thread.appendChild(row);scrollBottom();
return{think,thinkBody:tb,body,chips};}
async function ask(){
const msg=q.value.trim();if(!msg)return;
const pv=(sel.value||'').split('|');const provider=pv[0],model=pv[1];
if(!currentSession)await newSession();
renderMessage('user',msg);q.value='';go.disabled=true;
const live=newAssistantBubble();let tools=[];let buf='';let raw='';let rt=null;
const flush=()=>{if(rt){clearTimeout(rt);rt=null;}renderMd(live.body,raw);scrollBottom();};
const schedule=()=>{if(rt)return;rt=setTimeout(()=>{rt=null;renderMd(live.body,raw);scrollBottom();},60);};
try{const resp=await fetch('/chatlocal/api/chat/stream',{method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({session_id:currentSession,message:msg,provider:provider,model:model})});
const reader=resp.body.getReader();const dec=new TextDecoder();
while(true){const r=await reader.read();if(r.done)break;
buf+=dec.decode(r.value,{stream:true});let i;
while((i=buf.indexOf('\\n'))>=0){const line=buf.slice(0,i).trim();buf=buf.slice(i+1);
if(!line)continue;let ev;try{ev=JSON.parse(line);}catch(e){continue;}
if(ev.type==='thinking'){live.think.style.display='block';live.thinkBody.textContent+=ev.delta;
live.thinkBody.style.display='block';scrollBottom();}
else if(ev.type==='answer'){live.thinkBody.style.display='none';raw+=ev.delta;schedule();}
else if(ev.type==='tool'){
if(raw.trim()){live.think.style.display='block';
live.thinkBody.textContent+=(live.thinkBody.textContent?'\\n':'')+raw.trim();
raw='';renderMd(live.body,'');}
tools.push(ev.name);live.chips.textContent='used: '+tools.join(', ');}
else if(ev.type==='error'){raw+='\\n\\n[error: '+ev.message+']';schedule();}}}
}catch(e){raw+='\\n\\n[error: '+e+']';}
flush();go.disabled=false;refreshSessions();}
document.getElementById('new').onclick=newSession;
go.onclick=ask;
q.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}});
loadModels();refreshSessions();
"""


def _chat_ui() -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>"
        "<title>GeM assistant</title><style>" + _CSS + _CHAT_CSS + "</style>"
        "<script src='https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js'></script>"
        "<script src='https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js'></script>"
        "</head><body>"
        "<div class='chat-shell'>"
        "<aside class='sidebar'>"
        "<div class='sidebar-head'><button id='new'>＋ New session</button>"
        "<p style='margin:8px 0 0;font-size:12px;opacity:.7'><a href='/index'>← index</a> · "
        "<a href='/logout'>sign out</a></p></div>"
        "<div id='sessions'></div>"
        "</aside>"
        "<section class='chat-main'>"
        "<div class='chat-top'>"
        "<button id='menu' aria-label='Menu'>☰</button>"
        "<label for='model' class='muted'>Model</label>"
        "<select id='model' style='font-size:14px;padding:6px'></select>"
        "<span id='mstatus' class='muted' style='font-size:13px'></span>"
        "<span style='flex:1'></span>"
        "<a href='/logout' style='color:#0f5e8b;font-size:13px'>sign out</a>"
        "</div>"
        "<div id='thread'></div>"
        "<div class='composer'>"
        "<textarea id='q' rows='2' placeholder='Ask about bids, buyers, awards, documents…'></textarea>"
        "<button id='go'>Ask</button>"
        "</div>"
        "</section>"
        "</div><script>" + _CHAT_JS + "</script></body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype: str = "text/html; charset=utf-8", headers=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    # -- auth ---------------------------------------------------------------
    def _client_ip(self) -> str:
        fwd = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For")
        if fwd:
            return fwd.split(",")[0].strip()
        return self.client_address[0] or ""

    def _cookie_token(self) -> str:
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith(_COOKIE_NAME + "="):
                return part[len(_COOKIE_NAME) + 1:]
        return ""

    def _is_authed(self) -> bool:
        return _validate_session(self._cookie_token())

    def _cookie_header(self, token: str, clear: bool = False) -> str:
        if clear:
            return f"{_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        parts = [f"{_COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax"]
        if self.headers.get("X-Forwarded-Proto") == "https":
            parts.append("Secure")
        return "; ".join(parts)

    def _redirect(self, location: str) -> None:
        self._send(302, "", headers={"Location": location})

    def _handle_login(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        fields = urllib.parse.parse_qs(raw)
        username = (fields.get("username") or [""])[0].strip()
        password = (fields.get("password") or [""])[0]
        expect_user, expect_pw = _admin_credentials()
        if (
            not expect_pw
            or not hmac.compare_digest(username, expect_user)
            or not hmac.compare_digest(password, expect_pw)
        ):
            self._send(401, _login_page("invalid username or password"))
            return
        token = _issue_session()
        self._send(302, "", headers={"Location": "/", "Set-Cookie": self._cookie_header(token)})

    def do_GET(self):
        path = self.path.split("?")[0]
        # Public endpoints (no session required).
        if path == "/login":
            if self._is_authed():
                self._redirect("/")
            else:
                self._send(200, _login_page())
            return
        if path == "/logout":
            _drop_session(self._cookie_token())
            self._send(
                302,
                "",
                headers={"Set-Cookie": self._cookie_header("", clear=True), "Location": "/login"},
            )
            return
        if path == "/health":
            self._send(200, '{"ok": true}', "application/json")
            return

        # Everything else is behind the login.
        if not self._is_authed():
            is_api = (
                path == "/chatlocal/models"
                or path == "/chatlocal/sessions"
                or path.startswith("/chatlocal/sessions/")
                or path == "/mcp/tools"
            )
            if is_api:
                self._send(401, '{"error": "unauthorized"}', "application/json")
            else:
                self._redirect("/login")
            return

        if path == "/":
            self._send(200, _chat_ui())
        elif path == "/chatlocal":
            self._redirect("/")
        elif path == "/index":
            page = 1
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                if qs.startswith("page=") and qs[5:].isdigit():
                    page = max(1, int(qs[5:]))
            self._send(200, _index_page(page))
        elif path.startswith("/bid/"):
            bid_number = path[len("/bid/") :]
            self._send(200, _detail_page(bid_number))
        elif path == "/stats":
            self._send(200, _stats_page())
        elif path == "/chatlocal/models":
            self._send(200, json.dumps(list_models(), default=str), "application/json")
        elif path == "/chatlocal/sessions":
            self._send(200, json.dumps(chat_store.list_sessions(), default=str), "application/json")
        elif path.startswith("/chatlocal/sessions/"):
            sid = path[len("/chatlocal/sessions/") :]
            self._send(
                200,
                json.dumps({"session_id": sid, "messages": chat_store.get_messages(sid)}, default=str),
                "application/json",
            )
        elif path == "/mcp/tools":
            self._send(200, mcp_server.list_tools_json(_REGISTRY), "application/json")
        else:
            self._send(404, "<h1>404</h1>")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/login":
            self._handle_login()
            return
        if path.startswith("/chatlocal") or path.startswith("/mcp"):
            if not self._is_authed():
                self._send(401, '{"error": "unauthorized"}', "application/json")
                return
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length)
        if path == "/chatlocal/sessions":
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
                sid = chat_store.create_session(payload.get("provider"), payload.get("model"))
                self._send(200, json.dumps({"session_id": sid}), "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(exc)}), "application/json")
        elif path == "/chatlocal/api/chat/stream":
            self._handle_chat_stream(body)
        elif path == "/chatlocal/api/chat":
            self._handle_chat(body)
        elif path == "/mcp/call":
            self._send(200, mcp_server.call_tool_json(_REGISTRY, body), "application/json")
        else:
            self._send(404, '{"error": "not found"}', "application/json")

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if not self._is_authed():
            self._send(401, '{"error": "unauthorized"}', "application/json")
            return
        if path.startswith("/chatlocal/sessions/"):
            sid = path[len("/chatlocal/sessions/") :]
            try:
                chat_store.delete_session(sid)
                self._send(200, json.dumps({"ok": True}), "application/json")
            except Exception as exc:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(exc)}), "application/json")
        else:
            self._send(404, '{"error": "not found"}', "application/json")

    def _handle_chat(self, body: bytes) -> None:
        """Non-streaming chat (legacy endpoint): persist both sides with the caller's IP."""
        try:
            payload = json.loads(body.decode("utf-8"))
            message = (payload.get("message") or "").strip()
            if not message:
                self._send(400, json.dumps({"error": "message required"}), "application/json")
                return
            provider = payload.get("provider")
            model = payload.get("model")
            session_id = payload.get("session_id") or chat_store.create_session(provider, model)
            ip = self._client_ip()
            chat_store.add_message(session_id, "user", message, provider=provider, model=model, ip=ip)
            provider_obj = make_provider(provider, model)
            result = chat_agent.answer(message, _REGISTRY, provider=provider_obj)
            chat_store.add_message(
                session_id,
                "assistant",
                result.get("answer", ""),
                tool_rounds=result.get("tool_rounds", []),
                provider=provider,
                model=model,
                ip=ip,
            )
            result["session_id"] = session_id
            self._send(200, json.dumps(result, default=str), "application/json")
        except Exception as exc:  # noqa: BLE001 - surface to the UI, don't crash the server
            self._send(500, json.dumps({"error": str(exc)}), "application/json")

    # -- chat streaming ------------------------------------------------------
    def _stream_start(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _stream_event(self, obj: dict) -> None:
        line = json.dumps(obj, default=str) + "\n"
        self.wfile.write(line.encode("utf-8"))
        self.wfile.flush()

    def _handle_chat_stream(self, body: bytes) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            message = (payload.get("message") or "").strip()
            if not message:
                self._send(400, json.dumps({"error": "message required"}), "application/json")
                return
            provider = payload.get("provider")
            model = payload.get("model")
            session_id = payload.get("session_id") or chat_store.create_session(provider, model)
            history = chat_store.get_messages(session_id)
            ip = self._client_ip()
            chat_store.add_message(session_id, "user", message, provider=provider, model=model, ip=ip)
            provider_obj = make_provider(provider, model)
        except Exception as exc:  # noqa: BLE001 - headers not sent yet, safe to 500
            self._send(500, json.dumps({"error": str(exc)}), "application/json")
            return

        self._stream_start()
        try:
            for ev in chat_agent.answer_stream(
                message, _REGISTRY, history=history, provider=provider_obj
            ):
                if ev["type"] == "done":
                    chat_store.add_message(
                        session_id,
                        "assistant",
                        ev.get("answer", ""),
                        tool_rounds=ev.get("tool_rounds", []),
                        provider=provider,
                        model=model,
                        ip=ip,
                    )
                    ev["session_id"] = session_id
                self._stream_event(ev)
        except Exception as exc:  # noqa: BLE001 - headers already sent; stream an error event
            self._stream_event({"type": "error", "message": str(exc)})

    def log_message(self, *args):
        pass


def _source_snapshot() -> dict:
    return {
        str(p): (p.stat().st_mtime_ns, p.stat().st_size)
        for p in _SRC_ROOT.rglob("*.py")
    }


def _start_reload_watch() -> None:
    """Re-exec the process when a source file changes (dev convenience).

    The web service runs under launchd (KeepAlive) and would otherwise keep the
    code it loaded at startup forever, so an edit would silently do nothing until
    a manual `launchctl kickstart`. This watcher makes edits take effect on their
    own. Opt out with TENDERISING_NO_RELOAD=1.
    """
    if os.environ.get("TENDERISING_NO_RELOAD"):
        return
    baseline = _source_snapshot()

    def loop() -> None:
        while True:
            time.sleep(1.0)
            try:
                cur = _source_snapshot()
            except Exception:  # noqa: BLE001 - a transient stat error must not kill the watcher
                continue
            if cur != baseline:
                print("source change detected — reloading", flush=True)
                # Same PID is preserved across exec; the listening socket is
                # closed (PEP 446 non-inheritable fd) so the rebind succeeds.
                os.execv(
                    sys.executable,
                    [sys.executable, "-m", "tenderising.web.app", *sys.argv[1:]],
                )

    threading.Thread(target=loop, name="reload-watch", daemon=True).start()


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"serving on :{PORT}", flush=True)
    _start_reload_watch()
    server.serve_forever()


if __name__ == "__main__":
    main()
