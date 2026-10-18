import os, json, streamlit as st, pandas as pd

st.title("SepsisWatch Z — Bed Board")
audit_path = os.environ.get("AUDIT_PATH", "/data/audit.jsonl")
if os.path.exists(audit_path):
    rows = [json.loads(l) for l in open(audit_path)]
    df = pd.DataFrame(rows)
    st.dataframe(df.tail(50))
else:
    st.info("No alerts yet")
