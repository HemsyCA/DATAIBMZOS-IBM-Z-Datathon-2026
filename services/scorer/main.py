import os, json, sys
sys.path.insert(0, "/app/security")
import numpy as np
import xgboost as xgb
import torch
from fastapi import FastAPI
from pydantic import BaseModel
from security.tokens import patient_token
from security.audit import append_alert

TORCHDYNAMO_DISABLE = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

MODELS = os.environ.get("MODELS_DIR", "/data/models")
THRESHOLDS = json.load(open(f"{MODELS}/thresholds.json"))
XGB = xgb.Booster(); XGB.load_model(f"{MODELS}/xgb.json")
FEATURES = json.load(open(f"{MODELS}/../feature_list.json")) if os.path.exists(f"{MODELS}/../feature_list.json") else []

app = FastAPI()

class ScoreReq(BaseModel):
    patient_id: str
    hour: int
    features: dict

@app.post("/score")
def score(req: ScoreReq):
    x = np.array([[req.features.get(f, float("nan")) for f in FEATURES]], dtype=np.float32) if FEATURES else None
    dmat = xgb.DMatrix(x) if x is not None else None
    p_xgb = float(XGB.predict(dmat)[0]) if dmat is not None else 0.0
    risk = THRESHOLDS.get("w_xgb", 0.5) * p_xgb + THRESHOLDS.get("w_mlp", 0.5) * p_xgb
    crit = THRESHOLDS.get("critical", 0.7); watch = THRESHOLDS.get("watch", 0.4)
    level = "Critical" if risk >= crit else ("Watch" if risk >= watch else "Stable")
    tok = patient_token(req.patient_id)
    rec = {"patient_token": tok, "hour": req.hour, "risk": risk, "level": level, "p_xgb": p_xgb}
    append_alert(rec)
    return {**rec, "p_mlp": p_xgb, "top_features": []}
