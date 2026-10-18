"""Replays hospital B patients (never seen in training) as a 12-bed ICU ward.

Every tick = one clinical hour: the 12 beds are sent together to POST /score_batch, so the scorer
runs one NNPA batch per ward-hour. When a stay ends, the bed is given to the next patient in the pool.
Some beds hold patients who develop sepsis, starting ~24 h before onset so alerts appear early in the demo.
"""
import json
import math
import os
import time

import numpy as np
import pandas as pd
import requests

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
FEATURES_PATH = os.environ.get("FEATURES_PATH", f"{DATA_DIR}/data/processed/features.pkl")
DEMO_PATH = os.environ.get("DEMO_PATH", f"{DATA_DIR}/runtime/demo_patients.pkl")
SCORER = os.environ.get("SCORER_URL", "http://scorer:8000").rstrip("/")
DELAY = float(os.environ.get("DELAY_SEC", "1"))
BEDS = int(os.environ.get("BEDS", "12"))
N_SEPTIC = int(os.environ.get("N_SEPTIC", "16"))
N_OTHER = int(os.environ.get("N_OTHER", "32"))
LEAD_IN = int(os.environ.get("LEAD_IN_HOURS", "24"))
MAX_TICKS = int(os.environ.get("MAX_TICKS", "0"))       # 0 = run forever
SEED = int(os.environ.get("SEED", "7"))


def build_demo_set() -> pd.DataFrame:
    print("Building demo patient set from", FEATURES_PATH, flush=True)
    df = pd.read_pickle(FEATURES_PATH)
    df = df[df["split"].astype(str) == "test"].copy()
    df["patient_id"] = df["patient_id"].astype(str)
    per = df.groupby("patient_id").agg(hours=("hour", "size"), sepsis=("SepsisLabel", "max"))
    first = df[df["SepsisLabel"] == 1].groupby("patient_id")["hour"].min()
    per["first_label"] = first
    rng = np.random.default_rng(SEED)
    septic = per[(per.sepsis == 1) & (per.first_label >= LEAD_IN) & (per.hours >= per.first_label + 8)].index.to_numpy()
    other = per[(per.sepsis == 0) & (per.hours >= 36)].index.to_numpy()
    pick = list(rng.choice(septic, min(N_SEPTIC, len(septic)), replace=False)) + \
           list(rng.choice(other, min(N_OTHER, len(other)), replace=False))
    rng.shuffle(pick)
    demo = df[df["patient_id"].isin(pick)].copy()
    demo["start_hour"] = demo["patient_id"].map(per["first_label"].sub(LEAD_IN).clip(lower=0).fillna(0))
    demo = demo[demo["hour"] >= demo["start_hour"]]
    demo["order"] = demo["patient_id"].map({p: i for i, p in enumerate(pick)})
    demo = demo.sort_values(["order", "hour"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(DEMO_PATH), exist_ok=True)
    demo.to_pickle(DEMO_PATH)
    print(f"Demo set: {len(pick)} patients ({min(N_SEPTIC, len(septic))} develop sepsis), {len(demo):,} hours", flush=True)
    return demo


def wait_for_scorer():
    for _ in range(120):
        try:
            h = requests.get(f"{SCORER}/health", timeout=5).json()
            print("Scorer ready:", h, flush=True)
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("Scorer not reachable at " + SCORER)


def clean(v):
    if v is None:
        return None
    f = float(v)                      # also covers numpy float32
    return None if math.isnan(f) or math.isinf(f) else f


def main():
    demo = pd.read_pickle(DEMO_PATH) if os.path.exists(DEMO_PATH) else build_demo_set()
    skip = {"patient_id", "hospital", "hour", "split", "SepsisLabel", "start_hour", "order"}
    feat_cols = [c for c in demo.columns if c not in skip]
    stays = [g for _, g in demo.groupby("order", sort=True)]
    wait_for_scorer()

    nxt = 0
    beds = []
    for b in range(BEDS):
        beds.append({"bed": b + 1, "stay": stays[nxt % len(stays)], "pos": 0})
        nxt += 1

    tick = 0
    while not MAX_TICKS or tick < MAX_TICKS:
        rows = []
        for bd in beds:
            if bd["pos"] >= len(bd["stay"]):                        # discharge -> next patient
                bd["stay"], bd["pos"] = stays[nxt % len(stays)], 0
                nxt += 1
            r = bd["stay"].iloc[bd["pos"]]
            rows.append({"patient_id": str(r["patient_id"]), "hour": int(r["hour"]), "bed": bd["bed"],
                         "features": {c: clean(r[c]) for c in feat_cols}})
            bd["pos"] += 1
        try:
            out = requests.post(f"{SCORER}/score_batch", json={"rows": rows}, timeout=30).json()
            t = out["timing"]
            print(f"tick {tick:>5} | {t['batch_size']} beds | {t['counts']} | "
                  f"XGBoost {t['xgb_ms']:.2f} ms | MLP on {t['device']} {t['mlp_ms']:.2f} ms", flush=True)
        except Exception as e:
            print("scorer error:", e, flush=True)
        tick += 1
        time.sleep(DELAY)


if __name__ == "__main__":
    main()
