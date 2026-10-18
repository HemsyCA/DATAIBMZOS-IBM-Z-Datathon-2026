# Services — handoff

Four containers in one `docker-compose.yml`, all inside the z17 VM. No patient data leaves the machine.

```
replayer ──POST /score──▶ scorer ──▶ security (token, encrypt, audit) ──▶ alerts store ◀── dashboard
                            │
                            └── Critical only, async ──▶ granite (handoff note)
```

Suggested folders: `services/scorer/`, `services/replayer/`, `services/granite/`, `services/dashboard/` and `security/` at the repo root.

## Inputs already produced by the notebooks

All in `~/shared/sepsis/models/` on the VM (outside the repo):

| File | From | Used for |
|---|---|---|
| `xgb.json`, `xgb_config.json` | `03_xgboost` | XGBoost model, feature order, `best_iteration` |
| `mlp.pt`, `mlp_scaler.npz`, `mlp_config.json` | `04_nnpa_mlp` | MLP weights, median/mean/std for preprocessing, architecture |
| `thresholds.json` | `05_eval` | ensemble weights and the Critical / Watch thresholds |

Copy-paste loading code is at the end of notebooks 03 (XGBoost + per-alert top-3 features) and 04 (MLP on `nnpa`).

## `replayer`

Replays hospital B patients one clinical hour per second. **Do not recompute features online**: read the precomputed rows from `~/shared/sepsis/data/processed/features.pkl` where `split == "test"`, ordered by `patient_id`, `hour`, and send the 140 columns listed in `feature_list.json`. That is exactly what the scorer would see in production.

## `scorer` (FastAPI, `POST /score`)

Request:
```json
{"patient_id": "p100123", "hour": 37, "features": {"HR": 112.0, "Resp": 26.0, "...": "all 140 features, NaN allowed"}}
```

Logic:
1. `p_xgb` from XGBoost (no imputation, NaN allowed).
2. `p_mlp` from the MLP on the NNPA (NaN → median, then `(x - mean) / std`).
3. `risk = w_xgb * p_xgb + w_mlp * p_mlp` with the weights in `thresholds.json`.
4. `level = "Critical"` if `risk >= critical`, `"Watch"` if `risk >= watch`, otherwise `"Stable"`.
5. For Critical: top-3 XGBoost contributions (`pred_contribs=True`) → payload for Granite.

Response:
```json
{"patient_token": "…", "hour": 37, "risk": 0.71, "level": "Critical", "p_xgb": 0.74, "p_mlp": 0.68,
 "top_features": [{"feature": "Resp_6h_mean", "value": 26.4, "contribution": 1.9}]}
```

## `granite`

`python -m llama_cpp.server` with the Granite model from the Loan lab, built with zDNN. Critical patients only, asynchronous (the alert goes out first, the note arrives later).
Input: no identifiers — age range, hours in ICU and the top-3 features with value and trend. Output: a note of at most 80 words with a fixed template (what changed, why it is concerning, what to assess per hospital protocol). It never diagnoses or prescribes.

## `security/`

- Patient ID → HMAC-SHA256 token (`hmac`, `hashlib`; key from an environment variable).
- Age, sex and notes encrypted with AES-256-GCM via `cryptography`. **Not on pip for s390x**: use an Ubuntu 24.04 container with `apt install python3-cryptography` (built against OpenSSL, which uses CPACF).
- Every alert appended to a SHA3-256 hash-chained audit log; `verify_audit.py` detects any edited record.
- Containers run as non-root with AppArmor enabled.

## `dashboard` (Streamlit)

Bed board of 12 beds coloured by level, vital-sign trend for the selected bed, and the Granite note for Critical patients. Reads the stored alerts; it never calls the models directly.

## Platform notes (s390x)

- `fastapi`, `uvicorn` and `streamlit` install with pip.
- `pyarrow`, `duckdb` and `cryptography` have no s390x wheels on pip.
- Set `TORCHDYNAMO_DISABLE=1` before importing torch, as in the IBM Churn lab.
