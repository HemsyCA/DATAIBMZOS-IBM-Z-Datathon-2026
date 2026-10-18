"""SepsisWatch Z bed board. FastAPI + a self-contained HTML page (no pyarrow/Streamlit: not available on s390x).

GET /            the board (polls /api/state every REFRESH_SEC seconds)
GET /api/state   latest level per bed, current-stay history, notes and last batch timing
Reads only stored results; never calls the models.
"""
import json
import os
from collections import deque

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
RUNTIME = os.environ.get("RUNTIME_DIR", f"{DATA_DIR}/runtime")
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


@app.get("/api/state")
def state():
    scores = tail_jsonl(f"{RUNTIME}/scores.jsonl", BEDS * 120)
    notes = tail_jsonl(f"{RUNTIME}/notes.jsonl", 300)
    status = {}
    if os.path.exists(f"{RUNTIME}/status.json"):
        try:
            status = json.load(open(f"{RUNTIME}/status.json"))
        except json.JSONDecodeError:
            pass
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
        beds.append({"bed": b, "token": r["patient_token"][:10], "level": r["level"], "risk": r["risk"],
                     "icu_hours": r["icu_hours"], "vitals": r.get("vitals", {}), "p_xgb": r.get("p_xgb"),
                     "p_mlp": r.get("p_mlp"), "drivers": r.get("top_features", []),
                     "note": n["note"] if n else None, "note_source": n["source"] if n else None,
                     "note_hour": (n["hour"] + 1) if n else None,
                     "history": [{"t": x["icu_hours"], "risk": x["risk"], **x["vitals"]} for x in history[b][-72:]]})
    return {"beds": beds, "status": status}


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SepsisWatch Z · ICU bed board</title>
<style>
:root{--crit:#da1e28;--crit-bg:#fff1f1;--watch:#b28600;--watch-bg:#fcf4d6;--ok:#198038;--ok-bg:#defbe6;--ink:#161616;--muted:#525252;--line:#e0e0e0}
*{box-sizing:border-box}body{margin:0;font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:#fff}
.wrap{max-width:1320px;margin:0 auto;padding:24px 20px 40px}
h1{font-size:2rem;margin:0 0 4px}.cap{color:var(--muted);font-size:.9rem;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:18px}
.kpi .l{font-size:.85rem;color:var(--muted)}.kpi .v{font-size:1.9rem;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.bed{border-radius:10px;padding:12px 14px;border-left:8px solid;cursor:pointer;min-height:120px}
.bed.sel{outline:2px solid var(--ink)}
.bed .h{font-weight:600;display:flex;justify-content:space-between}.bed .risk{font-size:1.8rem;font-weight:700;line-height:1.2}
.bed .m{font-size:.8rem;color:#393939}
.detail{display:grid;grid-template-columns:3fr 2fr;gap:24px;margin-top:22px;border-top:1px solid var(--line);padding-top:18px}
.chart{width:100%;height:170px;border:1px solid var(--line);border-radius:6px;margin:6px 0 14px}
.legend span{display:inline-block;margin-right:14px;font-size:.8rem}.legend i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}
.note{background:#edf5ff;border-radius:8px;padding:12px 14px;color:#0043ce}.small{font-size:.8rem;color:var(--muted)}
@media (max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.kpis{grid-template-columns:repeat(2,1fr)}.detail{grid-template-columns:1fr}}
</style></head><body><div class="wrap">
<h1>SepsisWatch Z · ICU bed board</h1>
<div class="cap">Decision support for early sepsis warning on IBM LinuxONE (z17). Patients are pseudonymized tokens; age and sex are stored encrypted. Clinicians always decide.</div>
<div class="kpis" id="kpis"></div><div class="grid" id="grid"></div>
<div class="detail"><div id="left"></div><div id="right"></div></div>
</div>
<script>
const COL={Critical:["var(--crit)","var(--crit-bg)"],Watch:["var(--watch)","var(--watch-bg)"],Stable:["var(--ok)","var(--ok-bg)"]};
let sel=null;
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function line(hist,keys,colors,fixed){
  const W=600,H=160,P=28; if(!hist.length) return "";
  const xs=hist.map(h=>h.t),x0=Math.min(...xs),x1=Math.max(...xs,x0+1);
  let vals=[];keys.forEach(k=>hist.forEach(h=>{if(h[k]!=null)vals.push(h[k])}));
  let y0=fixed?fixed[0]:Math.min(...vals),y1=fixed?fixed[1]:Math.max(...vals);if(y1-y0<1e-6){y1=y0+1}
  const X=t=>P+(t-x0)/(x1-x0)*(W-P-8),Y=v=>H-18-(v-y0)/(y1-y0)*(H-30);
  let s=`<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
  [y0,(y0+y1)/2,y1].forEach(v=>{s+=`<line x1="${P}" x2="${W-8}" y1="${Y(v)}" y2="${Y(v)}" stroke="#e0e0e0"/><text x="2" y="${Y(v)+4}" font-size="10" fill="#6f6f6f">${fixed?Math.round(v*100)+"%":v.toFixed(0)}</text>`});
  keys.forEach((k,i)=>{const pts=hist.filter(h=>h[k]!=null).map(h=>`${X(h.t).toFixed(1)},${Y(h[k]).toFixed(1)}`).join(" ");
    s+=`<polyline fill="none" stroke="${colors[i]}" stroke-width="2" points="${pts}"/>`});
  s+=`<text x="${P}" y="${H-3}" font-size="10" fill="#6f6f6f">ICU hour ${x0}</text><text x="${W-8}" y="${H-3}" font-size="10" fill="#6f6f6f" text-anchor="end">${x1}</text></svg>`;
  return s;}
async function tick(){
  let d;try{d=await (await fetch("api/state")).json()}catch(e){return}
  const beds=d.beds.filter(b=>!b.empty),st=d.status||{},cnt={Critical:0,Watch:0,Stable:0};beds.forEach(b=>cnt[b.level]++);
  const lat=((st.xgb_ms||0)+(st.mlp_ms||0)).toFixed(1);
  document.getElementById("kpis").innerHTML=
    [["Critical",cnt.Critical],["Watch",cnt.Watch],["Stable",cnt.Stable],["Model · NN device",`${String(st.model||"–")} · ${String(st.device||"–").toUpperCase()}`],
     ["Ward scoring latency",`${lat} ms`]].map(([l,v])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`).join("")+
    `<div class="small" style="grid-column:1/-1">XGBoost ${(st.xgb_ms||0).toFixed(2)} ms + MLP on ${esc(String(st.device||"").toUpperCase())} ${(st.mlp_ms||0).toFixed(2)} ms for ${st.batch_size||0} beds</div>`;
  if(sel===null||!beds.find(b=>b.bed===sel)){const c=beds.find(b=>b.level==="Critical");sel=c?c.bed:(beds[0]||{}).bed}
  document.getElementById("grid").innerHTML=d.beds.map(b=>{
    if(b.empty)return `<div class="bed" style="border-color:#c6c6c6;background:#f4f4f4"><div class="h">Bed ${b.bed}</div><div class="m">empty</div></div>`;
    const [fg,bg]=COL[b.level],v=b.vitals||{};
    const vit=["HR","Resp","Temp","MAP"].filter(k=>v[k]!=null).map(k=>`${k} ${v[k]}`).join(" · ");
    return `<div class="bed ${b.bed===sel?"sel":""}" style="border-color:${fg};background:${bg}" onclick="sel=${b.bed};tick()">
      <div class="h"><span>Bed ${b.bed}</span><span style="color:${fg}">${b.level}</span></div>
      <div class="risk" style="color:${fg}">${Math.round(b.risk*100)}%</div>
      <div class="m">${esc(b.token)}… · ${b.icu_hours} h in ICU</div><div class="m">${esc(vit)}</div></div>`}).join("");
  const b=beds.find(x=>x.bed===sel);if(!b)return;
  document.getElementById("left").innerHTML=`<b>Sepsis risk over time — bed ${b.bed}</b>`+line(b.history,["risk"],["#0f62fe"],[0,1])+
    `<b>Vital signs (last value carried forward)</b>`+line(b.history,["HR","Resp","MAP"],["#0f62fe","#da1e28","#8a3ffc"])+
    `<div class="legend"><span><i style="background:#0f62fe"></i>HR</span><span><i style="background:#da1e28"></i>Resp</span><span><i style="background:#8a3ffc"></i>MAP</span></div>`;
  const drivers=(b.drivers||[]).map(x=>`<li>${esc(x.label)}: <b>${esc(x.value)}</b></li>`).join("");
  const src={granite:"IBM Granite (llama.cpp + zDNN), checked against the data",template_rejected:"template (Granite note failed the fact check)"}[b.note_source]||"template (Granite unavailable)";
  document.getElementById("right").innerHTML=`<b>Why this alert — bed ${b.bed} (${b.level}, risk ${Math.round(b.risk*100)}%)</b>`+
    (drivers?`<ul>${drivers}</ul>`:`<p class="small">Top drivers are shown for Critical patients.</p>`)+
    `<b>Handoff note</b>`+(b.note?`<div class="note">${esc(b.note)}</div><p class="small">Written when the patient became Critical (ICU hour ${b.note_hour}). Source: ${src}</p>`:`<p class="small">A note is written when a patient becomes Critical.</p>`)+
    `<p class="small">Scores: XGBoost ${(b.p_xgb??0).toFixed(2)} · MLP on ${esc(String(st.device||"cpu").toUpperCase())} ${(b.p_mlp??0).toFixed(2)} · alert model: ${esc(st.model||"")}</p>`;
}
tick();setInterval(tick,REFRESH_MS);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def board():
    return PAGE.replace("REFRESH_MS", str(int(REFRESH * 1000)))
