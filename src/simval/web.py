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


@app.get("/api/series")
def series(run_dir: str, selection: str = "protein and name CA"):
    from simval.viz import series_for
    return series_for(run_dir, selection=selection)


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>simval</title><meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;max-width:1000px;margin:1.5rem auto;padding:0 1rem;color:#222}
 h1{font-size:1.3rem} label{display:block;margin:.6rem 0 .15rem;color:#444}
 input,button,select{font:inherit;padding:.35rem .5rem;border:1px solid #bbb;border-radius:4px}
 button{background:#1a1a1a;color:#fff;border-color:#1a1a1a;cursor:pointer;margin-right:.4rem}
 button.alt{background:#fff;color:#1a1a1a}
 pre{background:#f5f5f5;padding:.6rem;border-radius:4px;overflow:auto;max-height:240px;font-size:12px}
 .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
 .card{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.6rem}
 canvas{max-width:100%}
</style></head><body>
<h1>simval <span style="color:#888;font-weight:normal">verification + reference oracle</span></h1>

<label>Run directory</label>
<input id="run" size="70" placeholder="/path/to/run-dir" value="">
<label>Selection</label>
<input id="sel" size="40" value="protein and name CA">

<div class="row" style="margin:1rem 0">
 <button onclick="plot()">Plot</button>
 <button class="alt" onclick="call('inspect')">Inspect</button>
 <button class="alt" onclick="call('diagnose')">Diagnose</button>
 <button class="alt" onclick="loadCases()">Cases</button>
 <select id="case"></select>
 <button class="alt" onclick="call('validate')">Validate</button>
</div>

<div class="cols">
 <div class="card"><h3>Series</h3>
  <select id="metric" onchange="renderSeries()"></select>
  <canvas id="seriesChart" height="200"></canvas>
 </div>
 <div class="card"><h3>Orbit (N-body)</h3>
  <canvas id="orbitChart" height="200"></canvas>
 </div>
 <div class="card" style="grid-column:1/-1"><h3>Field u(x,t) (waves)</h3>
  <canvas id="fieldCanvas" height="120"></canvas>
 </div>
</div>

<h3>Result</h3>
<pre id="out">—</pre>

<script>
let LAST=null, seriesChart=null, orbitChart=null;
async function loadCases(){const r=await(await fetch('/api/cases')).json();document.getElementById('case').innerHTML=r.cases.map(c=>`<option>${c}</option>`).join('');show(r);}
async function plot(){
  const run=document.getElementById('run').value, sel=document.getElementById('sel').value;
  const r=await(await fetch(`/api/series?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`)).json();
  LAST=r; show(r);
  const m=document.getElementById('metric'); m.innerHTML=Object.keys(r.series).map(k=>`<option>${k}</option>`).join('');
  renderSeries(); renderOrbit(r.orbit); renderField(r.field);
}
function renderSeries(){
  if(!LAST||!LAST.series) return;
  const key=document.getElementById('metric').value;
  const data=LAST.series[key]; if(!data) return;
  if(seriesChart) seriesChart.destroy();
  seriesChart=new Chart(document.getElementById('seriesChart'),{type:'line',
    data:{labels:data.map((_,i)=>i),datasets:[{label:key,data,borderColor:'#1a6',borderWidth:1.5,pointRadius:0,tension:.2}]},
    options:{plugins:{legend:{display:true}},scales:{x:{display:false}},animation:false}});
}
function renderOrbit(orbit){
  if(orbitChart) orbitChart.destroy();
  const el=document.getElementById('orbitChart');
  if(!orbit||!orbit.length){ el.getContext('2d').clearRect(0,0,el.width,el.height); return; }
  const cols=['#1a6','#a36','#06c','#c60','#36a','#6a6'];
  orbitChart=new Chart(el,{type:'scatter',
    datasets:orbit.map((o,i)=>({label:'body '+i,data:o.x.map((x,j)=>({x,y:o.y[j]})),borderColor:cols[i%6],borderWidth:1,pointRadius:.4,showLine:true})),
    options:{plugins:{legend:{display:true}},scales:{x:{title:{display:true,text:'x'}},y:{title:{display:true,text:'y'}}},animation:false}});
}
function renderField(field){
  const cv=document.getElementById('fieldCanvas'); const ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  if(!field||!field.length) return;
  const nt=field.length, nx=field[0].length;
  let mx=0; for(let i=0;i<nt;i++)for(let j=0;j<nx;j++)mx=Math.max(mx,Math.abs(field[i][j]));
  mx=mx||1;
  const w=cv.width=cv.clientWidth||600, h=cv.height;
  const pix={x:w/nx, y:h/nt};
  for(let i=0;i<nt;i++)for(let j=0;j<nx;j++){
    const v=field[i][j]/mx; // -1..1
    const r=v>0?Math.round(220*v):0, b=v<0?Math.round(-220*v):0, g=40*Math.abs(v);
    ctx.fillStyle=`rgb(${r},${g},${b})`;
    ctx.fillRect(j*pix.x,(nt-1-i)*pix.y,Math.ceil(pix.x)+1,Math.ceil(pix.y)+1);
  }
}
async function call(kind){
  const run=document.getElementById('run').value, sel=document.getElementById('sel').value, cs=document.getElementById('case').value;
  let url,opt={};
  if(kind==='inspect')url=`/api/inspect?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`;
  else if(kind==='diagnose'){url=`/api/diagnose?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`;opt.method='POST';}
  else if(kind==='validate'){url=`/api/validate?run_dir=${encodeURIComponent(run)}&case=${encodeURIComponent(cs)}&selection=${encodeURIComponent(sel)}`;opt.method='POST';}
  try{show(await(await fetch(url,opt)).json());}catch(e){show({error:String(e)});}
}
function show(o){document.getElementById('out').textContent=JSON.stringify(o,null,2);}
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
