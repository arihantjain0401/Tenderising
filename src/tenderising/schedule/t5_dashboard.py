"""T5 progress dashboard — tiny stdlib HTTP server, no dependencies.

Serves a self-contained HTML page plus /progress.json (aggregated per-worker
status). Reads only the T5 progress files; it never touches the curated DB.
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from tenderising.schedule.t5 import PROGRESS_DIR, STOP_FILE, T5_DIR

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>T5 snapshot progress</title>
<style>
:root{--bg:#0f1115;--fg:#e6e9ef;--muted:#8b93a3;--card:#191c23;--line:#2a2f3a;
--accent:#4f8cff;--ok:#2ecc71;--warn:#f1c40f;--err:#e74c3c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:24px}
h1{font-size:20px;margin:0 0 4px}h1 span{color:var(--muted);font-weight:400;font-size:13px}
.muted{color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:12px;margin:20px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat .v{font-size:24px;font-weight:600}.stat .k{color:var(--muted);font-size:12px;margin-top:2px}
.facets{margin:0 0 20px}.facets h2{font-size:13px;color:var(--muted);font-weight:500;margin:0 0 8px}
.facet{display:grid;grid-template-columns:180px 1fr 130px;gap:12px;align-items:center;padding:7px 0;font-size:13px}
.facet .name{color:var(--fg)}.facet .n{color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:500;font-size:12px}
tr:last-child td{border-bottom:none}.bar{height:8px;background:#262b36;border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--accent);transition:width .3s}
.pill{font-size:11px;padding:2px 8px;border-radius:99px}
.pill.running{background:rgba(46,204,113,.15);color:var(--ok)}
.pill.done{background:rgba(79,140,255,.15);color:var(--accent)}
.pill.stopped{background:rgba(241,196,15,.15);color:var(--warn)}
.pill.error{background:rgba(231,76,60,.15);color:var(--err)}
.foot{color:var(--muted);font-size:12px;margin-top:16px}
</style></head><body>
<h1>T5 snapshot <span id="sub"></span></h1>
<div class="grid" id="stats"></div>
<div class="facets" id="facets"></div>
<table><thead><tr><th>Worker</th><th>Status</th><th>Pages</th><th>Docs</th><th>Errors</th><th>Rate</th><th>Page #</th><th>Proxy</th></tr></thead>
<tbody id="rows"></tbody></table>
<div class="foot" id="foot"></div>
<script>
const fmt=n=>n==null?'—':n.toLocaleString();
async function tick(){
  try{
    const d=await (await fetch('/progress.json')).json();
    document.getElementById('sub').textContent=d.stopped?' · STOPPED':` · ${d.now}`;
    const s=document.getElementById('stats');
    s.innerHTML=[
      ['Pages done',`${fmt(d.done)} / ${fmt(d.total)}`],
      ['Docs fetched',fmt(d.docs)],
      ['Rate',`${d.rate.toFixed(2)} p/s`],
      ['ETA',d.eta],
      ['Errors',fmt(d.errors)],
      ['Proxied',`${d.proxied}/${d.n}`],
      ['Distinct IPs',fmt(d.distinct_ips)],
      ['Workers',`${d.running} running / ${d.n}`],
    ].map(([k,v])=>`<div class="stat"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');
    const fh=document.getElementById('facets');
    fh.innerHTML=(d.facets&&d.facets.length)
      ?('<h2>Facets — remaining pages (deep offset = slower)</h2>'+d.facets.map(f=>{
        const pct=f.remaining?Math.round(100*f.done/f.remaining):0;
        return `<div class="facet"><span class="name">${f.label}</span>
          <div class="bar"><i style="width:${pct}%"></i></div>
          <span class="n">${fmt(f.done)} / ${fmt(f.remaining)}</span></div>`;
      }).join(''))
      :'';
    const proxyCell=w=>{
      if(!w.proxy) return '<span class="muted">direct</span>';
      const ip=w.egress_ip?`<div class="muted" style="font-size:11px">${w.egress_ip}</div>`:'';
      return `<span>${w.proxy}</span>${ip}`;
    };
    const row=w=>{
      const pcls=w.status==='done'?'done':(w.status==='running'?'running':(w.status==='stopped'?'stopped':'error'));
      const tag=w.round?` <span class="muted">· ${w.round}</span>`:'';
      return `<tr><td>#${String(w.worker_id).padStart(2,'0')}${tag}</td>
        <td><span class="pill ${pcls}">${w.status}</span></td>
        <td>${fmt(w.pages_done)}</td>
        <td>${fmt(w.docs_fetched)}</td><td>${w.errors||0}</td>
        <td>${(w.rate||0).toFixed(2)} p/s</td>
        <td>${fmt(w.current_page)}</td>
        <td>${proxyCell(w)}</td></tr>`;
    };
    const t=document.getElementById('rows');
    let html=d.workers.map(row).join('')||'<tr><td colspan="8" class="muted">no workers yet</td></tr>';
    if(d.previous&&d.previous.length){
      html+='<tr><td colspan="8" style="background:#14161c;border-top:2px solid #2a2f3a" class="muted">Previous rounds — '+d.previous.length+' archived workers (already saved)</td></tr>';
      html+=d.previous.map(row).join('');
    }
    t.innerHTML=html;
    document.getElementById('foot').textContent=d.hint||'';
  }catch(e){document.getElementById('foot').textContent='error: '+e;}
}
setInterval(tick,1500);tick();
</script></body></html>"""


def page_html(progress_url: str = "/progress.json") -> str:
    """The dashboard HTML, with the JS polling endpoint substituted (so the same
    page works both standalone and mounted inside the main FastAPI app)."""
    return PAGE.replace("/progress.json", progress_url)


def _read_workers(directory: Path) -> list[dict]:
    """Read worker progress JSONs from a directory (sorted by worker id)."""
    workers: list[dict] = []
    if not directory.exists():
        return workers
    for p in sorted(directory.glob("worker_*.json")):
        try:
            workers.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return workers


def _read_run() -> dict:
    """Facet totals + run metadata from the latest run.json (written at run start)."""
    p = T5_DIR / "run.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def aggregate() -> dict:
    workers = _read_workers(PROGRESS_DIR)
    run = _read_run()

    # With work-stealing every worker shares the same remaining queue, so the
    # run's scope comes from run.json, not the sum of per-worker page totals.
    run_done_before = run.get("done_pages", 0)       # pages fetched before this run
    run_remaining = run.get("remaining_pages", 0)    # pages this run must fetch

    cur_done = cur_docs = cur_errors = 0
    rate_sum = 0.0
    running = 0
    facet_done: dict[str, int] = {}
    for d in workers:
        cur_done += d.get("pages_done", 0)
        cur_docs += d.get("docs_fetched", 0)
        cur_errors += d.get("errors", 0)
        if d.get("status") == "running":
            running += 1
            rate_sum += d.get("rate", 0.0) or 0.0
        for label, n in (d.get("facet_counts") or {}).items():
            facet_done[label] = facet_done.get(label, 0) + n

    # Per-facet progress for this run's scope (0 when the dashboard runs before any run).
    facets = []
    for f in run.get("facets", []):
        label = f.get("label")
        if label is None:
            continue
        remaining = f.get("remaining", f.get("pages", 0))
        done = facet_done.get(label, 0)
        facets.append({"label": label, "remaining": remaining, "done": done})

    proxied = sum(1 for d in workers if d.get("proxy"))
    distinct_ips = len({d.get("egress_ip") for d in workers if d.get("egress_ip")})

    previous = []
    prev_done = prev_docs = prev_errors = 0
    for rd in sorted(T5_DIR.glob("round*")):
        if not rd.is_dir():
            continue
        for d in _read_workers(rd):
            d = dict(d)
            d["round"] = rd.name
            previous.append(d)
            prev_done += d.get("pages_done", 0)
            prev_docs += d.get("docs_fetched", 0)
            prev_errors += d.get("errors", 0)

    # ETA from current-run remaining only (archived rounds are already done).
    has_run = bool(run)
    remaining = (run_remaining - cur_done) if has_run else 0
    eta = None
    if rate_sum > 0 and remaining > 0:
        secs = remaining / rate_sum
        eta = time.strftime("%H:%M:%S", time.gmtime(secs)) + " (h:m:s)"

    # Full-corpus totals. run.json's done_pages already covers archived rounds
    # (done_pages() scans every jsonl under data/t5/), so never double-count "previous".
    if has_run:
        total = run_done_before + run_remaining
        done = run_done_before + cur_done
    else:
        total = prev_done
        done = prev_done
    docs = cur_docs + prev_docs
    errors = cur_errors + prev_errors

    return {
        "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n": len(workers),
        "running": running,
        "stopped": STOP_FILE.exists(),
        "total": total,
        "done": done,
        "docs": docs,
        "errors": errors,
        "proxied": proxied,
        "distinct_ips": distinct_ips,
        "rate": rate_sum,
        "eta": eta or "—",
        "facets": facets,
        "n_workers": run.get("n_workers"),
        "workers": workers,
        "previous": previous,
        "hint": "stop: touch data/t5/stop  ·  work-stealing: idle workers pull remaining pages  ·  raw: data/t5/raw/  ·  dashboard refreshes every 1.5s",
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/progress.json":
            self._send(json.dumps(aggregate()).encode(), "application/json")
        else:
            self._send(PAGE.encode(), "text/html; charset=utf-8")

    def log_message(self, *a) -> None:  # quiet
        pass


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="t5-dashboard", description="T5 progress dashboard")
    ap.add_argument("--port", type=int, default=8071)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args(argv)
    srv = HTTPServer((args.host, args.port), Handler)
    print(f"T5 dashboard on http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
