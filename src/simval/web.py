"""Local-first web dashboard. Optional dep: pip install 'simval[web]'."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from simval import __version__, service

app = FastAPI(title="simval", version=__version__)


def _run(fn):
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


@app.get("/api/examples")
def examples():
    root = Path("examples")
    dirs = []
    if root.exists():
        for dp, _, fns in os.walk(str(root)):
            if any(f.endswith(".json") for f in fns):
                dirs.append(dp)
    return {"examples": sorted(dirs)}


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


def run(argv=None) -> None:
    import argparse
    import uvicorn

    p = argparse.ArgumentParser(prog="simval-web")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    a = p.parse_args(argv)
    uvicorn.run(app, host=a.host, port=a.port)


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>simval</title><meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/3dmol@2.4.2/build/3Dmol-min.js"></script>
<style>
*{box-sizing:border-box}
body{font:14px/1.6 -apple-system,system-ui,sans-serif;background:#0e0e0e;color:#ddd;margin:0}
.wrap{max-width:900px;margin:0 auto;padding:1.5rem 1rem}
h1{font-size:1.2rem;margin:0 0 .8rem;color:#fff}
h1 span{color:#555;font-weight:normal}
.bar{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;margin-bottom:.6rem}
input,select{font:inherit;padding:.4rem .5rem;border:1px solid #333;border-radius:4px;background:#1a1a1a;color:#ddd}
button{font:inherit;padding:.4rem .9rem;border:none;border-radius:4px;cursor:pointer}
.btn-go{background:#2a5;color:#fff}
.btn-ghost{background:#222;color:#aaa;border:1px solid #333}
.badge{padding:.15rem .6rem;border-radius:12px;font-size:.72rem;background:#1e3;color:#7df}
.pass{color:#5b8}.fail{color:#e55}
.cards{display:flex;flex-direction:column;gap:.8rem;margin-top:.8rem}
.card{background:#161616;border:1px solid #222;border-radius:8px;padding:1rem;display:none}
.card.on{display:block}
.card h3{font-size:.78rem;color:#666;text-transform:uppercase;letter-spacing:.5px;margin:0 0 .5rem}
.viewer{width:100%;height:340px;position:relative;background:#000;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:.82rem}
td,th{padding:.3rem .4rem;border-bottom:1px solid #222}
th{color:#666;text-align:left}
pre{background:#0a0a0a;padding:.6rem;border-radius:4px;overflow:auto;max-height:140px;font-size:11px;color:#888}
canvas{max-width:100%}
</style></head><body>
<div class="wrap">
<h1>simval <span>verify + render</span></h1>
<div class="bar">
<select id="picker" onchange="pick()" style="min-width:200px"></select>
<input id="run" size="44" placeholder="path or pick above" value="examples/openmm_lysozyme">
<input id="sel" size="16" value="protein and name CA">
</div>
<div class="bar">
<button class="btn-go" onclick="plot()">Load</button>
<button class="btn-ghost" onclick="diag()">Diagnose</button>
<span id="badge" style="margin-left:auto"></span>
</div>
<div class="cards">
<div class="card" id="c-verdict"><h3>Verdict</h3><div id="vbox"></div></div>
<div class="card" id="c-3d"><h3>Structure 3D</h3>
<div id="v3d" class="viewer"></div>
<div style="display:flex;gap:.4rem;align-items:center;margin-top:.3rem">
<input id="fs" type="range" min="0" max="0" oninput="frame()" style="flex:1">
<span id="fl" style="font-size:.7rem;color:#666"></span></div></div>
<div class="card" id="c-s"><h3>Series</h3>
<select id="met" onchange="rSer()" style="margin-bottom:.2rem"></select>
<canvas id="sc" height="150"></canvas></div>
<div class="card" id="c-orb"><h3>Orbit</h3>
<canvas id="oc" height="150"></canvas>
<input id="os" type="range" min="1" max="100" value="100" oninput="rOrb()" style="width:100%;margin-top:.2rem"></div>
<div class="card" id="c-fld"><h3>Field</h3><canvas id="fc" height="70"></canvas></div>
<div class="card" id="c-raw"><h3>Raw JSON</h3><pre id="raw"></pre></div>
</div></div>
<script>
let D=null,sC=null,oC=null,V=null,NF=0;
const $=id=>document.getElementById(id);
const off=()=>['c-verdict','c-3d','c-s','c-orb','c-fld','c-raw'].forEach(c=>$(c).classList.remove('on'));
const on=c=>$(c).classList.add('on');
async function loadPicker(){try{const r=await(await fetch('/api/examples')).json();$('picker').innerHTML='<option value="">-- pick --</option>'+r.examples.map(e=>`<option>${e}</option>`).join('');}catch(e){}}
function pick(){const v=$('picker').value;if(v){$('run').value=v;plot();}}
async function plot(){
  const r=$('run').value,s=$('sel').value;if(!r)return;
  let d;try{d=await(await fetch(`/api/series?run_dir=${encodeURIComponent(r)}&selection=${encodeURIComponent(s)}`)).json();}catch(e){$('raw').textContent=e;on('c-raw');return;}
  D=d;$('badge').innerHTML=`<span class="badge">${d.engine}</span>`;off();
  if(d.series&&Object.keys(d.series).length){const m=$('met');m.innerHTML=Object.keys(d.series).map(k=>`<option>${k}</option>`).join('');on('c-s');requestAnimationFrame(()=>rSer());}
  if(d.orbit&&d.orbit.length){on('c-orb');$('os').value=100;requestAnimationFrame(()=>rOrb());}
  if(d.field){on('c-fld');requestAnimationFrame(()=>rFld(d.field));}
  try{const fr=await(await fetch(`/api/frames?run_dir=${encodeURIComponent(r)}`)).json();NF=fr.n_frames||0;if(NF>0){$('fs').max=NF-1;$('fs').value=0;await r3d(0);on('c-3d');}}catch(e){}
}
async function r3d(f){
  const r=$('run').value;$('fl').textContent=`frame ${f}/${Math.max(0,NF-1)}`;
  let d;try{d=await(await fetch(`/api/structure?run_dir=${encodeURIComponent(r)}&frame=${f}&selection=protein`)).json();}catch(e){return;}
  if(!d.pdb)return;const el=$('v3d');if(V){V.removeAllModels();}else{V=$3Dmol.createViewer(el,{backgroundColor:'#000'});}
  V.addModel(d.pdb,'pdb');V.setStyle({},{cartoon:{color:'spectrum'}});V.zoomTo();V.render();}
function frame(){r3d(+$('fs').value);}
function rSer(){if(!D||!D.series)return;const k=$('met').value,v=D.series[k];if(!v)return;if(sC)sC.destroy();
sC=new Chart($('sc'),{type:'line',data:{labels:v.map((_,i)=>i),datasets:[{label:k,data:v,borderColor:'#5af',borderWidth:1.5,pointRadius:0,tension:.2}]},options:{plugins:{legend:{labels:{color:'#aaa'}}},scales:{x:{ticks:{color:'#555'}},y:{ticks:{color:'#555'}}},animation:false}});}
function rOrb(){if(oC)oC.destroy();const o=D&&D.orbit;if(!o||!o.length)return;
const up=Math.max(1,Math.round((+$('os').value/100)*o[0].x.length));const cs=['#5af','#f8a','#5fa','#fa5','#a5f','#5fa'];
oC=new Chart($('oc'),{type:'scatter',datasets:o.map((b,i)=>({label:'b'+i,data:b.x.slice(0,up).map((x,j)=>({x,y:b.y[j]})),borderColor:cs[i%6],borderWidth:1,pointRadius:.3,showLine:true})),options:{plugins:{legend:{labels:{color:'#aaa'}}},scales:{x:{ticks:{color:'#555'}},y:{ticks:{color:'#555'}}},animation:false}});}
function rFld(f){const cv=$('fc'),cx=cv.getContext('2d');cx.clearRect(0,0,cv.width,cv.height);if(!f||!f.length)return;
const nt=f.length,nx=f[0].length;let mx=0;for(let i=0;i<nt;i++)for(let j=0;j<nx;j++)mx=Math.max(mx,Math.abs(f[i][j]));mx=mx||1;
const w=cv.width=cv.clientWidth||400,h=cv.height,px={x:w/nx,y:h/nt};for(let i=0;i<nt;i++)for(let j=0;j<nx;j++){const v=f[i][j]/mx;cx.fillStyle=`rgb(${v>0?Math.round(180*v):0},${20*Math.abs(v)},${v<0?Math.round(-180*v):0})`;cx.fillRect(j*px.x,(nt-1-i)*px.y,Math.ceil(px.x)+1,Math.ceil(px.y)+1);}}
async function diag(){
  const r=$('run').value,s=$('sel').value;if(!r)return;
  let d;try{d=await(await fetch(`/api/diagnose?run_dir=${encodeURIComponent(r)}&selection=${encodeURIComponent(s)}`,{method:'POST'})).json();}catch(e){$('raw').textContent=e;on('c-raw');return;}
  on('c-verdict');const v=d.verdict.toUpperCase(),c=v==='PASS'?'pass':'fail';
  let h=`<div style="font-size:1.5rem;font-weight:bold" class="${c}">${v}</div><table><tr><th>Check</th><th style="text-align:right">Value</th><th style="text-align:right">Limit</th><th></th></tr>`;
  for(const r of d.diagnostics){const ok=r.passed;h+=`<tr><td>${r.name}</td><td style="text-align:right">${r.value.toExponential(2)}</td><td style="text-align:right">${r.threshold.toExponential(2)}</td><td class="${ok?'pass':'fail'}" style="font-weight:bold">${ok?'ok':'FAIL'}</td></tr>`;}
  h+='</table>';$('vbox').innerHTML=h;$('raw').textContent=JSON.stringify(d,null,2);on('c-raw');}
loadPicker();window.addEventListener('load',()=>setTimeout(plot,300));
</script></body></html>
"""
