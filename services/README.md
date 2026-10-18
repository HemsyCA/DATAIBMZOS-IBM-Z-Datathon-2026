# Services — SepsisWatch Z

Four services from **one image** (`services/Dockerfile`, built on the IBM LinuxONE Jupyter image), all inside the z17 VM. No patient data leaves the machine.

```
replayer ──POST /score_batch (12 beds / clinical hour)──▶ scorer ──▶ runtime/scores.jsonl ◀── dashboard (FastAPI + HTML :8501)
                                                           │  XGBoost (CPU, SIMD) + MLP on the Telum II NNPA
                                                           ├──▶ audit/alerts.jsonl  (SHA3-256 hash chain, Watch + Critical)
                                                           └──▶ granite (:8080, llama.cpp + zDNN) ──▶ runtime/notes.jsonl
```

| Service | Code | What it does |
|---|---|---|
| `scorer` | `services/scorer/main.py` | FastAPI. Scores a whole ward per call: XGBoost + MLP on `nnpa`, ensemble weights and Critical/Watch thresholds from `thresholds.json`. Tokenizes patient IDs (HMAC-SHA256), encrypts age/sex (AES-256-GCM), appends alerts to the audit chain, queues a Granite note when a patient becomes Critical. |
| `replayer` | `services/replayer/main.py` | Replays hospital B (never seen in training) as a 12-bed ward, one clinical hour per second. 16 of the 48 demo patients develop sepsis and start 24 h before onset. |
| `granite` | `services/granite/main.py` | IBM Granite 4.0 350M (big-endian GGUF for s390x) via llama.cpp with zDNN. Writes a ≤ 60-word handoff note from de-identified facts. If it is down or slow, the scorer writes a fixed template note instead (the alert never waits). |
| `dashboard` | `services/dashboard/main.py` | 12-bed board coloured by level, risk and vital-sign trends per bed, "why this alert" (clinical drivers only) and the handoff note. Reads stored results; never calls the models. Plain FastAPI + HTML because Streamlit needs `pyarrow`, which has no s390x build. |
| security | `security/` | `tokens.py`, `encryption.py`, `audit.py`, `verify_audit.py`. |

Everything the services read or write lives in `~/shared/sepsis/` on the VM (outside the repo): `models/` (from notebooks 03–05), `runtime/` and `audit/`.

## Run on the VM

```bash
cd ~/shared/DATAIBMZOS-IBM-Z-Datathon-2026
git pull

# 1. Granite model into the shared models folder (once)
docker exec notebook cp /home/ibm-user/granite-4.0-h-350m-base-be.f16.gguf /home/ibm-user/shared/sepsis/models/

# 2. Secrets + base image (once; creates .env, which is git-ignored)
bash scripts/make_env.sh

# 3. Build and start
docker compose up -d --build
docker compose ps                     # evidence 15
docker compose logs -f replayer       # one line per clinical hour: levels + XGBoost / NNPA latency
```

Dashboard from your laptop: `ssh -i Respaldo.pem -L 8501:localhost:8501 linux1@148.100.108.226`, then open http://localhost:8501.

Health check: `curl -s localhost:18000/health` → must show `"device": "nnpa"`.

### Plan B — without Docker Compose

If the image build fails, run the same code inside the existing `notebook` container:

```bash
bash scripts/make_env.sh
docker exec -it notebook bash /home/ibm-user/shared/DATAIBMZOS-IBM-Z-Datathon-2026/scripts/run_in_notebook.sh
# logs: ~/shared/sepsis/runtime/*.log      stop: docker exec notebook pkill -f "services\."
```
Check with `docker exec notebook curl -s localhost:8000/health`. The notebook container usually only publishes Jupyter's port, so open the dashboard through Jupyter's proxy if available (`http://<jupyter-url>/proxy/8501/`) or use Compose.

## Switch the alert model

The scorer always computes both XGBoost and the MLP on the NNPA; `MODEL` decides which score drives the levels, each with its own thresholds chosen on validation (`notebooks/05_eval` → `thresholds.json["per_model"]`). Thresholds cap both new false alarms (≤ 1 per patient-day for Critical) and alarm time (≤ 10% of non-sepsis patient-hours in Critical, ≤ 25% at Watch or above). `05_eval` also picks the best model on validation and prints which `MODEL=` to use (`thresholds.json["recommended_model"]`).

```bash
echo "MODEL=xgb" >> .env            # ensemble (default) | xgb | mlp
rm -f ~/shared/sepsis/runtime/*.jsonl ~/shared/sepsis/runtime/status.json   # clean board (optional)
docker compose up -d scorer replayer
curl -s localhost:18000/health      # shows "model"
```

Optional manual override: `CRITICAL_THRESHOLD=0.6` / `WATCH_THRESHOLD=0.4` in `.env` (then add them under `scorer.environment`).

## Evidence

| # | Command |
|---|---|
| 14 | `docker compose logs granite \| grep -i zdnn` |
| 15 | `docker compose ps` |
| 16 | `docker compose exec scorer python security/verify_audit.py` (green) |
| 17 | `cp ~/shared/sepsis/audit/alerts.jsonl ~/shared/sepsis/audit/tampered.jsonl && sed -i '5s/"risk": [0-9.]*/"risk": 0.01/' ~/shared/sepsis/audit/tampered.jsonl && docker compose exec scorer python security/verify_audit.py /data/sepsis/audit/tampered.jsonl` (red) |
| 22 | Dashboard with a Critical bed and its note |

## Notes

- `cryptography` has no pip wheel for s390x, so `security/encryption.py` calls OpenSSL's `libcrypto` directly (ctypes, `EVP_aes_256_gcm`), which runs on CPACF. `/health` shows `"encryption_backend": "openssl-libcrypto"`. The format is identical to `cryptography`'s AESGCM. If no backend is found, age/sex are not stored at all (never in plaintext).
- Restarting with new keys (`.env`) changes all tokens; delete `~/shared/sepsis/runtime/*.jsonl` and `audit/` for a clean demo.
- "Why this alert" and Granite notes use **physiology only**: measurement-pattern (`*_hours_since`, `*_measured`) and administrative fields (`Unit*`, `HospAdmTime`) are excluded from explanations even though the model uses them.
