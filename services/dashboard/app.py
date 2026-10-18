<<<<<<< HEAD
import os, json, html
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

AUDIT_PATH = os.environ.get("AUDIT_PATH", "/home/ibm-user/shared/sepsis/audit.jsonl")
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def board():
    rows = []
    if os.path.exists(AUDIT_PATH):
        rows = [json.loads(l) for l in open(AUDIT_PATH)]
    body = "".join(
        f"<tr><td>{r.get('patient_token','')[:12]}</td><td>{r.get('hour')}</td>"
        f"<td>{r.get('risk',0):.3f}</td><td>{r.get('level')}</td></tr>" for r in rows[-50:]
    )
    return f"<html><body><h1>SepsisWatch Z</h1><table border=1><tr><th>Token</th><th>Hour</th><th>Risk</th><th>Level</th></tr>{body}</table></body></html>"
=======
import os, json, streamlit as st, pandas as pd

st.title("SepsisWatch Z — Bed Board")
audit_path = os.environ.get("AUDIT_PATH", "/data/audit.jsonl")
if os.path.exists(audit_path):
    rows = [json.loads(l) for l in open(audit_path)]
    df = pd.DataFrame(rows)
    st.dataframe(df.tail(50))
else:
    st.info("No alerts yet")
>>>>>>> bd0cf8dee94e081bf4094c2612bd663bb5d9c78e
