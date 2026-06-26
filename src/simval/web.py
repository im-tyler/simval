"""Minimal local-first web dashboard. Proves the service API is UI-agnostic —
any future UI (notebook, full SPA, agent) replaces this thin layer without
touching the core. Optional dep: pip install 'simval[web]'."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from simval import __version__
from simval import service

app = FastAPI(title="simval", version=__version__)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return _HTML


@app.get("/api/engines")
def engines():
    return {"engines": service.list_engines()}


@app.get("/api/cases")
def cases():
    return {"cases": service.cases()}


@app.get("/api/inspect")
def inspect(run_dir: str, selection: str = "protein"):
    return service.inspect(run_dir, selection=selection)


@app.post("/api/diagnose")
def diagnose(run_dir: str, selection: str = "protein", out: str = "provenance.json"):
    return service.diagnose_run(run_dir, selection=selection, out=out)


@app.post("/api/validate")
def validate(run_dir: str, case: str, selection: str | None = None):
    return service.validate_run(run_dir, case, selection=selection)


@app.get("/api/compare")
def compare(run_a: str, run_b: str, selection: str = "protein and name CA"):
    return service.compare_runs(run_a, run_b, selection=selection)


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>simval</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;max-width:920px;margin:2rem auto;padding:0 1rem;color:#222}
 h1{font-size:1.4rem} label{display:block;margin:.6rem 0 .15rem;color:#444}
 input,button,select{font:inherit;padding:.35rem .5rem;border:1px solid #bbb;border-radius:4px}
 button{background:#1a1a1a;color:#fff;border-color:#1a1a1a;cursor:pointer;margin-right:.4rem}
 button.alt{background:#fff;color:#1a1a1a}
 pre{background:#f5f5f5;padding:.8rem;border-radius:4px;overflow:auto;max-height:420px}
 .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
 .pass{color:#080}.fail{color:#a00}
</style></head><body>
<h1>simval <span style="color:#888;font-weight:normal">deterministic MD verification + reference oracle</span></h1>

<label>Run directory (local path)</label>
<input id="run" size="60" placeholder="/path/to/run-dir" value="">
<label>Selection</label>
<input id="sel" size="40" value="protein and name CA">

<div class="row" style="margin:1rem 0">
 <button onclick="call('inspect')">Inspect</button>
 <button onclick="call('diagnose')">Diagnose</button>
 <button class="alt" onclick="loadCases()">Load cases</button>
</div>

<label>Reference case</label>
<div class="row"><select id="case"></select>
 <button class="alt" onclick="call('validate')">Validate vs case</button>
</div>

<h3>Result</h3>
<pre id="out">—</pre>

<script>
async function loadCases(){
  const r = await (await fetch('/api/cases')).json();
  const s = document.getElementById('case');
  s.innerHTML = r.cases.map(c=>`<option>${c}</option>`).join('');
  show(r);
}
async function call(kind){
  const run = document.getElementById('run').value;
  const sel = document.getElementById('sel').value;
  const cs = document.getElementById('case').value;
  let url, opt = {};
  if(kind==='inspect') url = `/api/inspect?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`;
  else if(kind==='diagnose'){ url = `/api/diagnose?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`; opt.method='POST'; }
  else if(kind==='validate'){ url = `/api/validate?run_dir=${encodeURIComponent(run)}&case=${encodeURIComponent(cs)}&selection=${encodeURIComponent(sel)}`; opt.method='POST'; }
  try{
    const r = await (await fetch(url, opt)).json();
    show(r);
  }catch(e){ show({error: String(e)}); }
}
function show(o){
  const el = document.getElementById('out');
  el.textContent = JSON.stringify(o, null, 2);
}
</script>
</body></html>
"""


def run(argv=None) -> None:
    import argparse
    import uvicorn

    p = argparse.ArgumentParser(prog="simval-web", description="simval local dashboard")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    uvicorn.run(app, host=a.host, port=a.port)
