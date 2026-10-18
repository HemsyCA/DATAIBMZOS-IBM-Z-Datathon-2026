import os, json, time, requests, pandas as pd

FEATURES_PATH = os.environ.get("FEATURES_PATH", "/data/features.pkl")
FEATURE_LIST = json.load(open(os.environ.get("FEATURE_LIST", "/data/feature_list.json")))
SCORER_URL = os.environ.get("SCORER_URL", "http://scorer:8000/score")
DELAY = float(os.environ.get("DELAY_SEC", "1"))

df = pd.read_pickle(FEATURES_PATH)
test = df[df["split"] == "test"] if "split" in df.columns else df
test = test.sort_values(["patient_id", "hour"])

for pid, g in test.groupby("patient_id", sort=False):
    for _, row in g.iterrows():
        payload = {"patient_id": str(row.get("patient_id")), "hour": int(row.get("hour", 0)),
                   "features": {f: (None if pd.isna(row.get(f)) else float(row.get(f))) for f in FEATURE_LIST}}
        try:
            r = requests.post(SCORER_URL, json=payload, timeout=10)
            print(pid, row.get("hour"), r.status_code, r.json().get("level"))
        except Exception as e:
            print("err", e)
        time.sleep(DELAY)
