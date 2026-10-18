"""SepsisWatch Z scorer: XGBoost + MLP on the Telum II NNPA, ensemble, alert levels.

POST /score_batch  {"rows": [{"patient_id", "hour", "bed", "features": {...}}]}  (one ICU ward per call)
POST /score        one row
GET  /health       models, device, thresholds

Side effects (all under DATA_DIR, on the VM, outside the repo):
  runtime/scores.jsonl  every scored patient-hour (token, bed, risk, level, vitals) -> dashboard
  runtime/status.json   last batch timing (XGBoost / NNPA latency)                -> dashboard
  runtime/notes.jsonl   handoff notes for Critical patients (Granite or template)  -> dashboard
  audit/alerts.jsonl    SHA3 hash-chained log of every Watch/Critical alert
"""
import os
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")   # before importing torch (IBM Churn lab pattern)

import json
import queue
import threading
import time
from datetime import datetime, timezone

import numpy as np
import requests
import torch
import torch.nn as nn
import xgboost as xgb
from fastapi import FastAPI
from pydantic import BaseModel

from security import encryption
from security.audit import append_alert
from security.tokens import patient_token

try:
    import torch_nnpa  # noqa: F401  registers the "nnpa" device
    NNPA_OK = torch.nnpa.is_available()
except Exception:
    NNPA_OK = False

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
MODEL_DIR = os.environ.get("MODELS_DIR", f"{DATA_DIR}/models")
RUNTIME = os.environ.get("RUNTIME_DIR", f"{DATA_DIR}/runtime")
GRANITE_URL = os.environ.get("GRANITE_URL", "")            # e.g. http://granite:8080/note ; empty = template notes
DEVICE = "nnpa" if NNPA_OK and os.environ.get("USE_NNPA", "1") == "1" else "cpu"
os.makedirs(RUNTIME, exist_ok=True)

# ----------------------------------------------------------------------------- models
xcfg = json.load(open(f"{MODEL_DIR}/xgb_config.json"))
FEATURES = xcfg["features"]                               # exact training order (ICULOS already dropped)
BEST = int(xcfg["best_iteration"])
BOOSTER = xgb.Booster()
BOOSTER.load_model(f"{MODEL_DIR}/xgb.json")

mcfg = json.load(open(f"{MODEL_DIR}/mlp_config.json"))
assert mcfg["features"] == FEATURES, "XGBoost and MLP were trained on different feature lists: re-run 03 and 04"
_sc = np.load(f"{MODEL_DIR}/mlp_scaler.npz")
MED, MEAN, STD = _sc["median"], _sc["mean"], _sc["std"]


def build_mlp(n, hidden, dropout):
    layers, prev = [], n
    for h in hidden:
        layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout)]
        prev = h
    return nn.Sequential(*layers, nn.Linear(prev, 1))


MLP = build_mlp(len(FEATURES), mcfg["hidden"], mcfg["dropout"])
MLP.load_state_dict(torch.load(f"{MODEL_DIR}/mlp.pt", map_location="cpu"))
MLP.eval().to(DEVICE)

thr = json.load(open(f"{MODEL_DIR}/thresholds.json"))
W_XGB = float(thr["weights"]["xgb"])
W_MLP = float(thr["weights"]["mlp"])
CRITICAL, WATCH = float(thr["critical"]), float(thr["watch"])

# Only physiology explains an alert to a nurse (no measurement-pattern or administrative fields)
NOT_CLINICAL = ("_hours_since", "_measured")
ADMIN = {"Unit1", "Unit2", "HospAdmTime", "ICULOS", "Age", "Gender"}
CLINICAL_IDX = np.array([i for i, f in enumerate(FEATURES)
                         if not f.endswith(NOT_CLINICAL) and f not in ADMIN])
VITALS = ["HR", "Resp", "Temp", "MAP", "SBP", "O2Sat"]
LABELS = {"HR": "Heart rate", "Resp": "Respiratory rate", "Temp": "Temperature", "MAP": "Mean arterial pressure",
          "SBP": "Systolic BP", "O2Sat": "O2 saturation", "Lactate": "Lactate", "WBC": "White cells",
          "Creatinine": "Creatinine", "BUN": "BUN", "Platelets": "Platelets", "shock_index": "Shock index",
          "SIRS": "SIRS score", "qSOFA": "qSOFA score", "FiO2": "FiO2", "Bilirubin_total": "Bilirubin"}


def label(f: str) -> str:
    base = f.split("_6h_")[0]
    suffix = {"mean": " (6 h mean)", "min": " (6 h min)", "max": " (6 h max)", "change": " (6 h change)"}
    tail = f.split("_6h_")[1] if "_6h_" in f else ""
    return LABELS.get(base, base) + suffix.get(tail, "")


# ----------------------------------------------------------------------------- runtime state
_io_lock = threading.Lock()
_last_level: dict[str, str] = {}
_note_q: "queue.Queue[dict]" = queue.Queue(maxsize=100)


def _append(path: str, rec: dict):
    with _io_lock, open(path, "a") as f:
        f.write(json.dumps(rec, default=float) + "\n")


def template_note(job: dict) -> str:
    drivers = "; ".join(f"{d['label']} {d['value']}" for d in job["drivers"]) or "multiple vital signs"
    return (f"Bed {job['bed']}: sepsis risk rose to {job['risk']:.0%} (Critical) after {job['icu_hours']} h in ICU. "
            f"Main changes: {drivers}. Please reassess at the bedside and follow the unit's sepsis protocol.")


def note_worker():
    while True:
        job = _note_q.get()
        text, source = None, "template"
        if GRANITE_URL:
            try:
                facts = (f"Bed {job['bed']}. {job['icu_hours']} h in ICU. Sepsis risk {job['risk']:.2f} (Critical). "
                         + "; ".join(f"{d['label']} {d['value']}" for d in job["drivers"]) + ".")
                r = requests.post(GRANITE_URL, json={"facts": facts}, timeout=90)
                r.raise_for_status()
                text = r.json().get("note", "").strip() or None
                source = "granite" if text else "template"
            except Exception as e:  # Granite down or slow: the alert already went out, use the template
                print("granite unavailable:", e)
        _append(f"{RUNTIME}/notes.jsonl", {"patient_token": job["patient_token"], "bed": job["bed"],
                                            "hour": job["hour"], "note": text or template_note(job),
                                            "source": source, "ts": datetime.now(timezone.utc).isoformat()})


threading.Thread(target=note_worker, daemon=True).start()

# ----------------------------------------------------------------------------- API
app = FastAPI(title="SepsisWatch Z scorer")


class Row(BaseModel):
    patient_id: str
    hour: int
    bed: int | None = None
    features: dict[str, float | None]


class Batch(BaseModel):
    rows: list[Row]


@app.get("/health")
def health():
    return {"status": "ok", "device": DEVICE, "nnpa_available": NNPA_OK, "n_features": len(FEATURES),
            "weights": {"xgb": W_XGB, "mlp": W_MLP}, "critical": CRITICAL, "watch": WATCH,
            "granite": bool(GRANITE_URL), "encryption": encryption.AVAILABLE}


def _matrix(rows: list[Row]) -> np.ndarray:
    return np.array([[np.nan if r.features.get(f) is None else r.features[f] for f in FEATURES] for r in rows],
                    dtype=np.float32)


@app.post("/score_batch")
def score_batch(batch: Batch):
    rows = batch.rows
    if not rows:
        return {"results": []}
    X = _matrix(rows)

    t0 = time.perf_counter()
    dm = xgb.DMatrix(X, feature_names=FEATURES)
    p_xgb = BOOSTER.predict(dm, iteration_range=(0, BEST + 1))
    xgb_ms = (time.perf_counter() - t0) * 1000

    Xm = np.where(np.isnan(X), MED, X)
    Xm = ((Xm - MEAN) / STD).astype(np.float32)
    t0 = time.perf_counter()
    with torch.no_grad():
        p_mlp = torch.sigmoid(MLP(torch.from_numpy(Xm).to(DEVICE))).cpu().numpy().ravel()
    mlp_ms = (time.perf_counter() - t0) * 1000

    risk = W_XGB * p_xgb + W_MLP * p_mlp
    level = np.where(risk >= CRITICAL, "Critical", np.where(risk >= WATCH, "Watch", "Stable"))

    crit_idx = np.flatnonzero(level == "Critical")
    contrib = {}
    if len(crit_idx):
        c = BOOSTER.predict(xgb.DMatrix(X[crit_idx], feature_names=FEATURES), pred_contribs=True,
                            iteration_range=(0, BEST + 1))[:, :-1]
        for k, i in enumerate(crit_idx):
            cc = c[k, CLINICAL_IDX]
            order = np.argsort(-cc)[:3]
            contrib[i] = [{"feature": FEATURES[CLINICAL_IDX[j]], "label": label(FEATURES[CLINICAL_IDX[j]]),
                           "value": None if np.isnan(X[i, CLINICAL_IDX[j]]) else round(float(X[i, CLINICAL_IDX[j]]), 1),
                           "contribution": round(float(cc[j]), 3)} for j in order if cc[j] > 0]

    ts = datetime.now(timezone.utc).isoformat()
    results = []
    for i, r in enumerate(rows):
        tok = patient_token(r.patient_id)
        rec = {"patient_token": tok, "bed": r.bed, "hour": r.hour, "icu_hours": r.hour + 1,
               "risk": round(float(risk[i]), 4), "level": str(level[i]),
               "p_xgb": round(float(p_xgb[i]), 4), "p_mlp": round(float(p_mlp[i]), 4),
               "top_features": contrib.get(i, []), "ts": ts}
        vitals = {v: (None if r.features.get(v) is None else round(float(r.features[v]), 1)) for v in VITALS}
        _append(f"{RUNTIME}/scores.jsonl", {**rec, "vitals": vitals,
                                             "age_enc": encryption.encrypt(r.features.get("Age")),
                                             "sex_enc": encryption.encrypt(r.features.get("Gender"))})
        if rec["level"] != "Stable":
            append_alert({k: rec[k] for k in ("patient_token", "bed", "hour", "risk", "level", "top_features")})
        prev = _last_level.get(tok)
        if rec["level"] == "Critical" and prev != "Critical":
            try:
                _note_q.put_nowait({**rec, "drivers": rec["top_features"]})
            except queue.Full:
                pass
        _last_level[tok] = rec["level"]
        results.append(rec)

    status = {"ts": ts, "device": DEVICE, "batch_size": len(rows), "xgb_ms": round(xgb_ms, 3),
              "mlp_ms": round(mlp_ms, 3), "counts": {lv: int((level == lv).sum()) for lv in ("Critical", "Watch", "Stable")}}
    with _io_lock, open(f"{RUNTIME}/status.json", "w") as f:
        json.dump(status, f)
    return {"results": results, "timing": status}


@app.post("/score")
def score(row: Row):
    out = score_batch(Batch(rows=[row]))
    return {**out["results"][0], "timing": out["timing"]}
