"""SepsisWatch Z bed board. FastAPI + a self-contained HTML page (no pyarrow/Streamlit: not available on s390x).

GET /            the board (polls /api/state every REFRESH_SEC seconds)
GET /api/state   latest level per bed, current-stay history, notes, last batch timing and alert thresholds
Reads only stored results; never calls the models.
"""
import json
import os
from collections import deque

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
RUNTIME = os.environ.get("RUNTIME_DIR", f"{DATA_DIR}/runtime")
MODELS = os.environ.get("MODELS_DIR", f"{DATA_DIR}/models")
REFRESH = float(os.environ.get("REFRESH_SEC", "2"))
BEDS = int(os.environ.get("BEDS", "12"))

app = FastAPI(title="SepsisWatch Z bed board")


def tail_jsonl(path, n):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        out = []
        for line in deque(f, maxlen=n):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:   # line being written right now
                pass
        return out


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def thresholds_for(model):
    """Critical / Watch cut-offs of the model that drives the alerts (from notebooks/05_eval)."""
    t = read_json(f"{MODELS}/thresholds.json")
    per = (t.get("per_model") or {}).get(model or "", {})
    crit, watch = per.get("critical", t.get("critical")), per.get("watch", t.get("watch"))
    return {"critical": crit, "watch": watch}


@app.get("/api/state")
def state():
    scores = tail_jsonl(f"{RUNTIME}/scores.jsonl", BEDS * 120)
    notes = tail_jsonl(f"{RUNTIME}/notes.jsonl", 300)
    status = read_json(f"{RUNTIME}/status.json")
    latest, history = {}, {}
    for r in scores:                                   # file order = time order
        b = r.get("bed")
        if b is None:
            continue
        h = history.setdefault(b, [])
        if h and (h[-1]["patient_token"] != r["patient_token"] or r["hour"] < h[-1]["hour"]):
            h.clear()                                  # new patient in the bed or replayer restart
        h.append({"patient_token": r["patient_token"], "hour": r["hour"], "icu_hours": r["icu_hours"],
                  "risk": r["risk"], "vitals": r.get("vitals", {})})
        latest[b] = r
    notes_by_key = {}                                  # (token, bed) -> notes in time order
    for n in notes:
        notes_by_key.setdefault((n["patient_token"], n.get("bed")), []).append(n)
    beds = []
    for b in range(1, BEDS + 1):
        r = latest.get(b)
        if r is None:
            beds.append({"bed": b, "empty": True})
            continue
        # only a note written in THIS bed during THIS stay (patients can come back in another bed when the demo loops)
        stay_start, now = history[b][0]["hour"], r["hour"]
        cands = [x for x in notes_by_key.get((r["patient_token"], b), []) if stay_start <= x["hour"] <= now]
        n = cands[-1] if cands else None
        beds.append({"bed": b, "token": r["patient_token"][:8], "level": r["level"], "risk": r["risk"],
                     "icu_hours": r["icu_hours"], "vitals": r.get("vitals", {}), "p_xgb": r.get("p_xgb"),
                     "p_mlp": r.get("p_mlp"), "drivers": r.get("top_features", []),
                     "note": n["note"] if n else None, "note_source": n["source"] if n else None,
                     "note_hour": (n["hour"] + 1) if n else None,
                     "history": [{"t": x["icu_hours"], "risk": x["risk"], **x["vitals"]} for x in history[b][-72:]]})
    return {"beds": beds, "status": status, "thresholds": thresholds_for(status.get("model"))}


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SepsisWatch Z: ICU bed board</title>
<style>
:root{--red:#c62828;--red-bg:#fdecea;--amber:#8a6100;--amber-bg:#fff4d6;--green:#2e7d32;--green-bg:#eef7ee;
--ink:#1f2328;--muted:#5b636b;--line:#d8dde3;--panel:#f6f8fa;--sel:#1f5fa8}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;font-family:Arial,Helvetica,sans-serif;color:var(--ink);background:#fff;font-size:14px;line-height:1.35}
.wrap{max-width:1500px;margin:0 auto;padding:14px 18px;min-height:100%;display:flex;flex-direction:column}
header{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:2px solid var(--ink);padding-bottom:8px}
h1{font-size:22px;margin:0}
h2{font-size:15px;margin:0 0 6px}
.sub{color:var(--muted);font-size:13px}
.clock{color:var(--muted);font-size:12px;text-align:right;white-space:nowrap}
.main{display:grid;grid-template-columns:1.1fr 1fr;gap:20px;margin-top:10px;flex:1}
.bar{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap}
.key{display:flex;gap:6px;flex-wrap:wrap}
.key span{border-left:5px solid;padding:2px 8px;font-size:12px;background:var(--panel)}
.key b{margin-right:4px}
.counts{font-size:13px}.counts b{font-size:18px;margin:0 3px 0 10px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.bed{border:1px solid var(--line);border-left:7px solid;border-radius:5px;padding:7px 9px;cursor:pointer;background:#fff;position:relative}
.bed.sel{outline:3px solid var(--sel);outline-offset:1px}
.bed .top{display:flex;justify-content:space-between;align-items:center}
.bed .name{font-weight:bold;font-size:15px}
.bed .tag{font-weight:bold;font-size:11px;padding:1px 6px;border-radius:3px}
.bed .risk{font-size:26px;font-weight:bold;line-height:1.15}
.bed .risk small{font-size:12px;font-weight:normal;color:var(--muted);margin-left:4px}
.bed .meta{font-size:11.5px;color:var(--muted)}
.bed .abn{font-size:11.5px;color:var(--red);font-weight:bold;min-height:15px}
.side{border-left:1px solid var(--line);padding-left:20px;min-width:0}
.showing{font-size:12px;color:var(--muted);margin-bottom:4px}
.showing a{color:var(--sel);cursor:pointer;text-decoration:underline}
.chart{width:100%;height:auto;display:block}
.charts3{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}
.ct{font-size:11.5px;font-weight:bold}
table.why{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:10px}
table.why th{text-align:left;font-size:11px;color:var(--muted);font-weight:normal;border-bottom:1px solid var(--line);padding:3px 5px}
table.why td{border-bottom:1px solid var(--line);padding:4px 5px}
.note{border:1px solid var(--line);border-left:5px solid var(--sel);background:#f3f7fc;border-radius:4px;padding:8px 10px;font-size:14px}
.hint{font-size:11.5px;color:var(--muted);margin-top:4px}
details.sys{margin-top:12px;background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:8px 12px;font-size:12.5px}
details.sys summary{cursor:pointer;font-weight:bold;font-size:13px}
details.sys .cols{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:8px}
details.sys .cols b{display:block}
@media (max-width:1100px){.main{grid-template-columns:1fr}.side{border-left:0;padding-left:0;border-top:1px solid var(--line);padding-top:12px}details.sys .cols{grid-template-columns:1fr 1fr}}
@media (max-width:700px){.grid{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div class="wrap">
<header>
  <div><h1>SepsisWatch Z: ICU bed board</h1>
  <div class="sub">Risk that each patient develops sepsis in the next hours. It tells the nurse who to check first; it does not diagnose.</div></div>
  <div class="clock" id="clock"></div>
</header>
<div class="main">
  <section>
    <div class="bar"><div class="key" id="key"></div><div class="counts" id="counts"></div></div>
    <div class="grid" id="grid"></div>
    <details class="sys"><summary>How this board works</summary><div class="cols" id="sys"></div></details>
  </section>
  <section class="side"><div class="showing" id="showing"></div><div id="detail"></div></section>
</div>
</div>
<script>
const LV={Critical:{fg:"var(--red)",bg:"var(--red-bg)",word:"High risk",act:"check now"},
          Watch:{fg:"var(--amber)",bg:"var(--amber-bg)",word:"Watch",act:"re-check soon"},
          Stable:{fg:"var(--green)",bg:"var(--green-bg)",word:"Stable",act:"routine care"}};
// Usual adult ranges, only to help read the numbers (not the hospital's protocol)
const REF={HR:{n:"Heart rate",s:"heart rate",u:"/min",lo:60,hi:100},Resp:{n:"Breathing rate",s:"breathing",u:"/min",lo:12,hi:20},
  Temp:{n:"Temperature",s:"temperature",u:"°C",lo:36,hi:38},MAP:{n:"Mean blood pressure",s:"blood pressure",u:"mmHg",lo:65,hi:110},
  SBP:{n:"Systolic blood pressure",u:"mmHg",lo:100,hi:140},O2Sat:{n:"Oxygen saturation",s:"oxygen",u:"%",lo:94,hi:100},
  Lactate:{n:"Lactate",u:"",lo:0,hi:2},WBC:{n:"White blood cells",u:"x1000/µL",lo:4,hi:12},
  Creatinine:{n:"Creatinine",u:"mg/dL",lo:0.6,hi:1.2},BUN:{n:"Urea (BUN)",u:"mg/dL",lo:7,hi:20},
  Platelets:{n:"Platelets",u:"x1000/µL",lo:150,hi:450},Bilirubin_total:{n:"Bilirubin",u:"mg/dL",lo:0.1,hi:1.2},
  Alkalinephos:{n:"Alkaline phosphatase",u:"IU/L",lo:44,hi:147},shock_index:{n:"Shock index (heart rate / systolic BP)",u:"",lo:0.5,hi:0.9},
  SIRS:{n:"SIRS criteria met",u:"of 4",lo:0,hi:1},qSOFA:{n:"qSOFA criteria met",u:"of 2",lo:0,hi:1},
  FiO2:{n:"Oxygen given (FiO2)",u:"",lo:0.21,hi:0.4},Glucose:{n:"Glucose",u:"mg/dL",lo:70,hi:180},
  Potassium:{n:"Potassium",u:"mmol/L",lo:3.5,hi:5.0},Hgb:{n:"Hemoglobin",u:"g/dL",lo:12,hi:17},
  pH:{n:"Blood pH",u:"",lo:7.35,hi:7.45},HCO3:{n:"Bicarbonate",u:"mmol/L",lo:22,hi:28},
  PTT:{n:"Clotting time (PTT)",u:"s",lo:25,hi:35},BaseExcess:{n:"Base excess",u:"mmol/L",lo:-2,hi:2},AST:{n:"Liver enzyme (AST)",u:"IU/L",lo:10,hi:40},
  Calcium:{n:"Calcium",u:"mg/dL",lo:8.5,hi:10.5},Chloride:{n:"Chloride",u:"mmol/L",lo:96,hi:106},Magnesium:{n:"Magnesium",u:"mg/dL",lo:1.7,hi:2.4},
  Phosphate:{n:"Phosphate",u:"mg/dL",lo:2.5,hi:4.5},Hct:{n:"Hematocrit",u:"%",lo:36,hi:50},SaO2:{n:"Arterial oxygen saturation",u:"%",lo:94,hi:100},
  PaCO2:{n:"Blood CO2 (PaCO2)",u:"mmHg",lo:35,hi:45},Fibrinogen:{n:"Fibrinogen",u:"mg/dL",lo:200,hi:400},TroponinI:{n:"Troponin I",u:"ng/mL",lo:0,hi:0.04},
  Bilirubin_direct:{n:"Direct bilirubin",u:"mg/dL",lo:0,hi:0.3},DBP:{n:"Diastolic blood pressure",u:"mmHg",lo:60,hi:90}};
const WIN={mean:"average of last 6 h",min:"lowest in last 6 h",max:"highest in last 6 h",change:"change over last 6 h"};
let sel=null,pinned=false;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct=x=>Math.round((x||0)*100);
function flag(k,v){const r=REF[k];if(!r||v==null)return"";return v>r.hi?"high":v<r.lo?"low":"normal"}
function fmt(v){return v==null?"not measured":(Math.abs(v)>=100?Math.round(v):Math.round(v*10)/10)}
function pick(b){sel=b;pinned=true;tick()}
function follow(){pinned=false;sel=null;tick()}

function chart(hist,key,opt){
  const W=opt.w||600,H=opt.h||150,L=30,R=6,T=6,B=16;const pts=hist.filter(h=>h[key]!=null);
  if(pts.length<2)return`<svg class="chart" viewBox="0 0 ${W} ${H}"><text x="${W/2}" y="${H/2}" font-size="13" fill="#5b636b" text-anchor="middle">not enough measurements yet</text></svg>`;
  const x0=hist[0].t,x1=Math.max(hist[hist.length-1].t,x0+1);
  let vals=pts.map(h=>h[key]);if(opt.band)vals.push(opt.band[0],opt.band[1]);
  let y0=opt.fixed?opt.fixed[0]:Math.min(...vals),y1=opt.fixed?opt.fixed[1]:Math.max(...vals);const pad=(y1-y0)*0.08||1;if(!opt.fixed){y0-=pad;y1+=pad}
  const X=t=>L+(t-x0)/(x1-x0)*(W-L-R),Y=v=>T+(1-(v-y0)/(y1-y0))*(H-T-B);
  let s=`<svg class="chart" viewBox="0 0 ${W} ${H}">`;
  if(opt.band){const a=Math.max(opt.band[0],y0),b=Math.min(opt.band[1],y1);if(b>a)s+=`<rect x="${L}" y="${Y(b)}" width="${W-L-R}" height="${Y(a)-Y(b)}" fill="#e3f2e3"/>`}
  (opt.lines||[]).forEach(l=>{s+=`<line x1="${L}" x2="${W-R}" y1="${Y(l.v)}" y2="${Y(l.v)}" stroke="${l.c}" stroke-dasharray="5 4"/><text x="${L+4}" y="${Y(l.v)-3}" font-size="11" fill="${l.c}">${l.t}</text>`});
  [y0,y1].forEach(v=>{s+=`<text x="1" y="${Y(v)+4}" font-size="11" fill="#5b636b">${opt.fixed?Math.round(v*100)+"%":Math.round(v)}</text>`});
  s+=`<polyline fill="none" stroke="${opt.c||"#1f2328"}" stroke-width="2.2" points="${pts.map(h=>X(h.t).toFixed(1)+","+Y(h[key]).toFixed(1)).join(" ")}"/>`;
  const last=pts[pts.length-1];s+=`<circle cx="${X(last.t)}" cy="${Y(last[key])}" r="3.5" fill="${opt.c||"#1f2328"}"/>`;
  s+=`<text x="${L}" y="${H-2}" font-size="11" fill="#5b636b">${opt.w?"h "+x0:"ICU hour "+x0}</text><text x="${W-R}" y="${H-2}" font-size="11" fill="#5b636b" text-anchor="end">now${opt.w?"":" (hour "+x1+")"}</text></svg>`;
  return s}

function trend(b){const h=b.history;if(h.length<2)return"new patient";const prev=h[Math.max(0,h.length-7)].risk,d=pct(b.risk)-pct(prev);
  if(Math.abs(d)<3)return"steady";return(d>0?"up ":"down ")+Math.abs(d)+" pts in 6 h"}
function outOfRange(v){return["HR","Resp","Temp","MAP"].filter(k=>{const f=flag(k,v[k]);return f==="high"||f==="low"}).map(k=>REF[k].s+" "+flag(k,v[k]))}

async function tick(){
  let d;try{d=await(await fetch("api/state")).json()}catch(e){return}
  const beds=d.beds.filter(b=>!b.empty),st=d.status||{},th=d.thresholds||{},cnt={Critical:0,Watch:0,Stable:0};
  beds.forEach(b=>cnt[b.level]++);
  document.getElementById("clock").innerHTML=st.ts?`Updated ${new Date(st.ts).toLocaleTimeString()}<br>Demo: 1 ICU hour every few seconds`:"waiting for data";
  const cut={Critical:th.critical!=null?`${pct(th.critical)}%+`:"",Watch:th.watch!=null?`${pct(th.watch)} to ${pct(th.critical)-1}%`:"",Stable:th.watch!=null?`under ${pct(th.watch)}%`:""};
  document.getElementById("key").innerHTML=["Critical","Watch","Stable"].map(l=>`<span style="border-left-color:${LV[l].fg}"><b style="color:${LV[l].fg}">${LV[l].word}</b>${LV[l].act}${cut[l]?", "+cut[l]:""}</span>`).join("");
  document.getElementById("counts").innerHTML=["Critical","Watch","Stable"].map(l=>`<b style="color:${LV[l].fg}">${cnt[l]}</b>${LV[l].word.toLowerCase()}`).join("");
  // Follow mode: show the highest-risk bed until someone clicks a bed
  if(!pinned||!beds.find(b=>b.bed===sel)){pinned=pinned&&!!beds.find(b=>b.bed===sel);if(!pinned){const ok=beds.filter(b=>b.history.length>=4),pool=ok.length?ok:beds;const top=[...pool].sort((a,b)=>b.risk-a.risk)[0];sel=top?top.bed:null}}
  document.getElementById("grid").innerHTML=d.beds.map(b=>{
    if(b.empty)return`<div class="bed" style="border-left-color:#c4c9cf;background:var(--panel)"><div class="name">Bed ${b.bed}</div><div class="meta">empty</div></div>`;
    const L=LV[b.level],ab=outOfRange(b.vitals||{});
    return`<div class="bed ${b.bed===sel?"sel":""}" style="border-left-color:${L.fg}" onclick="pick(${b.bed})">
      <div class="top"><span class="name">Bed ${b.bed}</span><span class="tag" style="color:${L.fg};background:${L.bg}">${L.word}</span></div>
      <div class="risk" style="color:${L.fg}">${pct(b.risk)}%<small>risk</small></div>
      <div class="meta">${esc(trend(b))}, ${b.icu_hours} h in ICU</div>
      <div class="abn">${ab.length?esc(ab.join(", ")):""}</div></div>`}).join("");
  const b=beds.find(x=>x.bed===sel);if(!b)return;const L=LV[b.level];
  document.getElementById("showing").innerHTML=pinned?`Showing bed ${b.bed} (you selected it). <a onclick="follow()">Follow the highest-risk bed</a>`:`Showing the highest-risk bed (updates automatically). Click any bed to see its details.`;
  const v=b.vitals||{};
  const lines=[];if(th.critical!=null)lines.push({v:th.critical,c:"#c62828",t:"high risk"});if(th.watch!=null)lines.push({v:th.watch,c:"#8a6100",t:"watch"});
  const rows=(b.drivers||[]).map(x=>{const base=(x.feature||"").split("_6h_")[0],win=(x.feature||"").split("_6h_")[1],r=REF[base];
    const name=(r?r.n:x.label)+(win?` (${WIN[win]||win})`:"");const f=win==="change"?"":flag(base,x.value);
    const val=x.value==null?"not measured":(win==="change"&&x.value>0?"+":"")+fmt(x.value)+(r&&r.u?" "+r.u:"");
    const usual=r&&win!=="change"?`${r.lo} to ${r.hi}`:"";const bad=f==="high"||f==="low";
    return`<tr><td>${esc(name)}</td><td style="${bad?"color:var(--red);font-weight:bold":""}">${esc(val)}${bad?" ("+f+")":""}</td><td>${esc(usual)}</td></tr>`}).join("");
  const SRC={granite:"Written by IBM Granite on the z17 and checked against the patient's data.",
    template_pending:"Standard note shown right away. IBM Granite is writing a fuller note; it replaces this one only if it passes the fact check.",
    template_rejected:"Standard note. The IBM Granite draft was rejected because it did not match the patient's data.",
    template_backlog:"Standard note. IBM Granite was busy with other alerts.",template:"Standard note. IBM Granite was not available."};
  document.getElementById("detail").innerHTML=
    `<h2>Bed ${b.bed}: <span style="color:${L.fg}">${L.word}</span>, ${pct(b.risk)}% risk <span class="hint">(${b.icu_hours} h in ICU, protected ID ${esc(b.token)})</span></h2>`+
    chart(b.history,"risk",{fixed:[0,1],h:140,c:"#1f2328",lines})+
    `<div class="charts3">`+[["HR","#1f5fa8"],["Resp","#1f5fa8"],["MAP","#1f5fa8"]].map(([k,c])=>{const f=flag(k,v[k]),bad=f==="high"||f==="low";
      return`<div><div class="ct">${REF[k].n}: <span style="${bad?"color:var(--red)":""}">${v[k]==null?"n/a":fmt(v[k])+" "+REF[k].u}${bad?" "+f:""}</span></div>${chart(b.history,k,{w:300,h:130,c,band:[REF[k].lo,REF[k].hi]})}</div>`}).join("")+`</div>`+
    (rows?`<div class="hint" style="margin:0 0 2px">What raised the risk most:</div><table class="why"><tr><th>Measurement</th><th>Patient</th><th>Usual range</th></tr>${rows}</table>`
         :`<p class="hint">The main reasons are listed when a patient is at high risk. Green band = usual range.</p>`)+
    `<h2>Handoff note for the nurse</h2>`+(b.note?`<div class="note">${esc(b.note)}</div><div class="hint">${SRC[b.note_source]||SRC.template} Note from ICU hour ${b.note_hour}.</div>`
         :`<p class="hint">A short note is written when a patient becomes high risk.</p>`);
  const dev=String(st.device||"").toUpperCase(),ms=((st.xgb_ms||0)+(st.mlp_ms||0)).toFixed(1);
  const MODEL={mlp:"A neural network",xgb:"Gradient-boosted trees (XGBoost)",ensemble:"The average of a neural network and XGBoost"}[st.model]||esc(st.model||"");
  document.getElementById("sys").innerHTML=
    `<div><b>Risk model</b>${MODEL}, trained on one hospital system and tested on another. Risk = chance of sepsis within the next hours.</div>`+
    `<div><b>Speed on IBM z17</b>${dev==="NNPA"?`The neural network runs on the z17's on-chip AI accelerator: ${(st.mlp_ms||0).toFixed(2)} ms for ${st.batch_size||0} beds`:`Scoring runs on the z17 CPU`} (${ms} ms for the whole ward with XGBoost).</div>`+
    `<div><b>Privacy</b>Patient IDs are replaced by an irreversible code. ${st.encryption?"Age and sex are stored encrypted by the z17 crypto hardware (CPACF).":"Age and sex are not stored."} Data never leaves the machine.</div>`+
    `<div><b>Audit</b>Every alert is saved in a tamper-evident log (each record is linked to the previous one with a SHA-3 hash).</div>`;
}
tick();setInterval(tick,REFRESH_MS);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def board():
    return PAGE.replace("REFRESH_MS", str(int(REFRESH * 1000)))
