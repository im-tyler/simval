"""Minimal local-first web dashboard. Proves the service API is UI-agnostic —
any future UI (notebook, full SPA, agent) replaces this thin layer without
touching the core. Optional dep: pip install 'simval[web]'."""
from __future__ import annotations


from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from simval import __version__
from simval import service

app = FastAPI(title="simval", version=__version__)


def _run(fn):
    """Wrap a service call so a bad run-dir/case returns HTTP 400, not 500."""
    try:
        return fn()
    except (FileNotFoundError, ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


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
    return _run(lambda: service.inspect(run_dir, selection=selection))


@app.post("/api/diagnose")
def diagnose(run_dir: str, selection: str = "protein", out: str = "provenance.json"):
    return _run(lambda: service.diagnose_run(run_dir, selection=selection, out=out))


@app.post("/api/validate")
def validate(run_dir: str, case: str, selection: str | None = None):
    return _run(lambda: service.validate_run(run_dir, case, selection=selection))


@app.get("/api/compare")
def compare(run_a: str, run_b: str, selection: str = "protein and name CA"):
    return _run(lambda: service.compare_runs(run_a, run_b, selection=selection))


@app.get("/api/series")
def series(run_dir: str, selection: str = "protein and name CA"):
    from simval.viz import series_for
    return _run(lambda: series_for(run_dir, selection=selection))


@app.get("/api/frames")
def frames(run_dir: str):
    from simval.viz import frame_count
    return _run(lambda: {"n_frames": frame_count(run_dir)})


@app.get("/api/structure")
def structure(run_dir: str, frame: int = 0, selection: str = "protein"):
    from simval.viz import structure_pdb
    return _run(lambda: {"pdb": structure_pdb(run_dir, frame=frame, selection=selection)})


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>simval</title><meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/3dmol@2.4.2/build/3Dmol-min.js"></script>
<style>
 body{font:14px/1.5 -apple-system,system-ui,sans-serif;max-width:1100px;margin:1.5rem auto;padding:0 1rem;color:#222}
 h1{font-size:1.3rem} label{display:block;margin:.6rem 0 .15rem;color:#444}
 input,button,select{font:inherit;padding:.35rem .5rem;border:1px solid #bbb;border-radius:4px}
 button{background:#1a1a1a;color:#fff;border-color:#1a1a1a;cursor:pointer;margin-right:.4rem}
 button.alt{background:#fff;color:#1a1a1a}
 pre{background:#f5f5f5;padding:.6rem;border-radius:4px;overflow:auto;max-height:200px;font-size:12px}
 .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
 .cols{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
 .card{background:#fafafa;border:1px solid #eee;border-radius:6px;padding:.6rem}
 canvas{max-width:100%}
 .viewer{width:100%;height:300px;position:relative;background:#fff;border:1px solid #ddd}
 .slide{width:100%}
</style></head><body>
<h1>simval <span style="color:#888;font-weight:normal">verify + render</span></h1>

<label>Run directory</label>
<input id="run" size="70" placeholder="/path/to/run-dir" value="">
<label>Selection (MD) / pass-through for other domains</label>
<input id="sel" size="40" value="protein and name CA">

<div class="row" style="margin:1rem 0">
 <button onclick="plot()">Plot</button>
 <button class="alt" onclick="load3d()">Load 3D</button>
 <button class="alt" onclick="call('diagnose')">Diagnose</button>
 <button class="alt" onclick="call('inspect')">Inspect</button>
 <button class="alt" onclick="loadCases()">Cases</button>
 <select id="case"></select>
 <button class="alt" onclick="call('validate')">Validate</button>
</div>

<div class="cols">
 <div class="card" style="grid-column:1/-1"><h3>Structure 3D (MD)</h3>
  <div id="viewer3d" class="viewer"></div>
  <div class="row" style="margin-top:.4rem">
   <input id="frameSlider" class="slide" type="range" min="0" max="0" value="0" oninput="onFrame()">
   <span id="frameLabel">—</span>
  </div>
 </div>
 <div class="card"><h3>Series</h3>
  <select id="metric" onchange="renderSeries()"></select>
  <canvas id="seriesChart" height="180"></canvas>
 </div>
 <div class="card"><h3>Orbit (N-body)</h3>
  <canvas id="orbitChart" height="180"></canvas>
  <div class="row" style="margin-top:.4rem">
   <input id="orbitSlider" class="slide" type="range" min="1" max="100" value="100" oninput="renderOrbit()">
  </div>
 </div>
 <div class="card" style="grid-column:1/-1"><h3>Field u(x,t) (waves)</h3>
  <canvas id="fieldCanvas" height="100"></canvas>
 </div>
</div>

<h3>Result</h3>
<pre id="out">—</pre>

<script>
let LAST=null, seriesChart=null, orbitChart=null, VWR=null, NFRAMES=0, CURFRAME=0, SEL='protein';
async function loadCases(){const r=await(await fetch('/api/cases')).json();document.getElementById('case').innerHTML=r.cases.map(c=>`<option>${c}</option>`).join('');show(r);}
async function plot(){
  const run=document.getElementById('run').value, sel=document.getElementById('sel').value;
  SEL=sel;
  const r=await(await fetch(`/api/series?run_dir=${encodeURIComponent(run)}&selection=${encodeURIComponent(sel)}`)).json();
  LAST=r; show(r);
  const m=document.getElementById('metric'); m.innerHTML=Object.keys(r.series).map(k=>`<option>${k}</option>`).join('');
  const os=document.getElementById('orbitSlider'); os.value=os.max; os.disabled = !(r.orbit&&r.orbit.length);
  renderSeries(); renderOrbit(); renderField(r.field);
}
async function load3d(){
  const run=document.getElementById('run').value;
  try{
    const fr=await(await fetch(`/api/frames?run_dir=${encodeURIComponent(run)}`)).json();
    NFRAMES=Math.max(1,fr.n_frames||1);
  }catch(e){NFRAMES=1;}
  const sl=document.getElementById('frameSlider'); sl.max=NFRAMES-1; sl.value=0;
  CURFRAME=0; await render3d(0);
}
async function render3d(frame){
  const run=document.getElementById('run').value;
  document.getElementById('frameLabel').textContent=`frame ${frame}/${NFRAMES-1}`;
  let r; try{r=await(await fetch(`/api/structure?run_dir=${encodeURIComponent(run)}&frame=${frame}&selection=${encodeURIComponent(SEL)}`)).json();}
  catch(e){show({error:String(e)});return;}
  if(!r.pdb){return;}
  const el=document.getElementById('viewer3d');
  if(VWR){VWR.removeAllModels();} else {VWR=$3Dmol.createViewer(el,{backgroundColor:'#ffffff'});}
  VWR.addModel(r.pdb,'pdb');
  VWR.setStyle({},{cartoon:{color:'spectrum'},licorice:{radius:0.10,colorscheme:'element'}});
  VWR.zoomTo(); VWR.render();
}
function onFrame(){const f=+document.getElementById('frameSlider').value; CURFRAME=f; render3d(f);}
function renderSeries(){
  if(!LAST||!LAST.series) return;
  const key=document.getElementById('metric').value; const data=LAST.series[key]; if(!data) return;
  if(seriesChart) seriesChart.destroy();
  seriesChart=new Chart(document.getElementById('seriesChart'),{type:'line',
    data:{labels:data.map((_,i)=>i),datasets:[{label:key,data,borderColor:'#1a6',borderWidth:1.5,pointRadius:0,tension:.2}]},
    options:{plugins:{legend:{display:true}},scales:{x:{display:false}},animation:false}});
}
function renderOrbit(){
  if(orbitChart) orbitChart.destroy();
  const el=document.getElementById('orbitChart');
  const orbit=LAST&&LAST.orbit;
  if(!orbit||!orbit.length){ el.getContext('2d').clearRect(0,0,el.width,el.height); return; }
  const upto=Math.max(1, Math.round((+document.getElementById('orbitSlider').value/100)*orbit[0].x.length));
  const cols=['#1a6','#a36','#06c','#c60','#36a','#6a6'];
  orbitChart=new Chart(el,{type:'scatter',
    datasets:orbit.map((o,i)=>({label:'body '+i,data:o.x.slice(0,upto).map((x,j)=>({x,y:o.y[j]})),borderColor:cols[i%6],borderWidth:1,pointRadius:.4,showLine:true})),
    options:{plugins:{legend:{display:true}},scales:{x:{title:{display:true,text:'x'}},y:{title:{display:true,text:'y'}}},animation:false}});
}
function renderField(field){
  const cv=document.getElementById('fieldCanvas'); const ctx=cv.getContext('2d');
  ctx.clearRect(0,0,cv.width,cv.height);
  if(!field||!field.length) return;
  const nt=field.length, nx=field[0].length;
  let mx=0; for(let i=0;i<nt;i++)for(let j=0;j<nx;j++)mx=Math.max(mx,Math.abs(field[i][j])); mx=mx||1;
  const w=cv.width=cv.clientWidth||600, h=cv.height; const pix={x:w/nx,y:h/nt};
  for(let i=0;i<nt;i++)for(let j=0;j<nx;j++){
    const v=field[i][j]/mx; const r=v>0?Math.round(220*v):0, b=v<0?Math.round(-220*v):0, g=40*Math.abs(v);
    ctx.fillStyle=`rgb(${r},${g},${b})`; ctx.fillRect(j*pix.x,(nt-1-i)*pix.y,Math.ceil(pix.x)+1,Math.ceil(pix.y)+1);
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
