"""SepsisWatch Z bed board (Streamlit). Reads only stored results; never calls the models."""
import html
import json
import os
import time
from collections import deque

import pandas as pd
import streamlit as st

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
RUNTIME = os.environ.get("RUNTIME_DIR", f"{DATA_DIR}/runtime")
REFRESH = float(os.environ.get("REFRESH_SEC", "2"))
BEDS = int(os.environ.get("BEDS", "12"))
COLORS = {"Critical": ("#da1e28", "#fff1f1"), "Watch": ("#b28600", "#fcf4d6"), "Stable": ("#198038", "#defbe6")}

st.set_page_config(page_title="SepsisWatch Z", page_icon="🩺", layout="wide")
st.markdown("""
<style>
.block-container {padding-top: 1.2rem;}
.bed {border-radius: 10px; padding: 12px 14px; border-left: 8px solid; margin-bottom: 12px; min-height: 128px;}
.bed .hdr {font-size: 1.05rem; font-weight: 600; margin-bottom: 4px; overflow: hidden;}
.bed .lvl {font-weight: 700; float: right;}
.bed .risk {font-size: 1.8rem; font-weight: 700; line-height: 1.1;}
.bed .meta {font-size: .82rem; color: #393939;}
</style>""", unsafe_allow_html=True)


def tail_jsonl(path, n):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in deque(f, maxlen=n)]


scores = tail_jsonl(f"{RUNTIME}/scores.jsonl", BEDS * 96)
notes = tail_jsonl(f"{RUNTIME}/notes.jsonl", 200)
status = json.load(open(f"{RUNTIME}/status.json")) if os.path.exists(f"{RUNTIME}/status.json") else {}

st.title("SepsisWatch Z · ICU bed board")
st.caption("Decision support for early sepsis warning on IBM LinuxONE (z17). Patients are pseudonymized tokens; "
           "age and sex are stored encrypted. Clinicians always decide.")

if not scores:
    st.info("Waiting for the first scores from the replayer…")
    if REFRESH > 0:
        time.sleep(REFRESH)
        st.rerun()
    st.stop()

df = pd.DataFrame(scores)
latest = df.sort_values("ts").groupby("bed").tail(1).set_index("bed")
note_by_token = {n["patient_token"]: n for n in notes}

c1, c2, c3, c4, c5 = st.columns(5)
counts = latest["level"].value_counts()
c1.metric("Critical", int(counts.get("Critical", 0)))
c2.metric("Watch", int(counts.get("Watch", 0)))
c3.metric("Stable", int(counts.get("Stable", 0)))
c4.metric("Neural net device", str(status.get("device", "–")).upper())
c5.metric("Ward scoring latency", f"{status.get('xgb_ms', 0) + status.get('mlp_ms', 0):.1f} ms",
          help=f"XGBoost {status.get('xgb_ms', 0):.2f} ms + MLP {status.get('mlp_ms', 0):.2f} ms "
               f"for {status.get('batch_size', 0)} beds")

cols = st.columns(4)
for i, bed in enumerate(range(1, BEDS + 1)):
    with cols[i % 4]:
        if bed not in latest.index:
            st.markdown(f"<div class='bed' style='border-color:#c6c6c6;background:#f4f4f4'><div class='hdr'>Bed {bed}</div>"
                        f"<div class='meta'>empty</div></div>", unsafe_allow_html=True)
            continue
        r = latest.loc[bed]
        fg, bg = COLORS.get(r["level"], ("#525252", "#f4f4f4"))
        v = r["vitals"] or {}
        vit = " · ".join(f"{k} {v[k]:g}" for k in ("HR", "Resp", "Temp", "MAP") if v.get(k) is not None)
        st.markdown(
            f"<div class='bed' style='border-color:{fg};background:{bg}'>"
            f"<div class='hdr'>Bed {bed}<span class='lvl' style='color:{fg}'>{r['level']}</span></div>"
            f"<div class='risk' style='color:{fg}'>{r['risk']:.0%}</div>"
            f"<div class='meta'>{html.escape(str(r['patient_token'])[:10])}… · {int(r['icu_hours'])} h in ICU</div>"
            f"<div class='meta'>{html.escape(vit)}</div></div>", unsafe_allow_html=True)

st.divider()
left, right = st.columns([3, 2])
crit_beds = [int(b) for b in latest.index if latest.loc[b, "level"] == "Critical"]
default = crit_beds[0] if crit_beds else int(latest.index.min())
bed = left.selectbox("Bed detail", sorted(latest.index.astype(int)), index=sorted(latest.index.astype(int)).index(default))
r = latest.loc[bed]
hist = df[(df["bed"] == bed) & (df["patient_token"] == r["patient_token"])].sort_values("ts")
restart = (hist["hour"].diff() < 0).to_numpy().nonzero()[0]      # replayer restarted: keep the current run only
if len(restart):
    hist = hist.iloc[restart[-1]:]
vit = pd.json_normalize(hist["vitals"]).set_index(hist["icu_hours"].to_numpy())
left.markdown(f"**Sepsis risk over time — bed {bed}**")
left.line_chart(pd.Series(hist["risk"].to_numpy(), index=hist["icu_hours"].to_numpy(), name="risk"), height=180)
left.markdown("**Vital signs (last value carried forward)**")
left.line_chart(vit[[c for c in ("HR", "Resp", "MAP") if c in vit]], height=200)

with right:
    st.markdown(f"**Why this alert** — bed {bed} ({r['level']}, risk {r['risk']:.0%})")
    drivers = r["top_features"] if isinstance(r["top_features"], list) else []
    if drivers:
        for d in drivers:
            st.markdown(f"- {d['label']}: **{d['value']}**")
    else:
        st.caption("Top drivers are shown for Critical patients.")
    n = note_by_token.get(r["patient_token"])
    st.markdown("**Handoff note**")
    if n:
        src = "IBM Granite (zDNN)" if n["source"] == "granite" else "template (Granite unavailable)"
        st.info(n["note"])
        st.caption(f"Source: {src} · written at ICU hour {n['hour'] + 1}")
    else:
        st.caption("A note is written when a patient becomes Critical.")
    st.caption(f"Ensemble: XGBoost {r['p_xgb']:.2f} · MLP on {str(status.get('device', 'cpu')).upper()} {r['p_mlp']:.2f}")

if REFRESH > 0:          # auto-refresh (REFRESH_SEC=0 disables it)
    time.sleep(REFRESH)
    st.rerun()
