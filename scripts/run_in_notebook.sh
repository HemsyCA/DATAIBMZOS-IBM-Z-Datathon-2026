#!/usr/bin/env bash
# Plan B (no docker compose): run the 4 services inside the existing "notebook" container.
# From the VM:  docker exec -it notebook bash /home/ibm-user/shared/DATAIBMZOS-IBM-Z-Datathon-2026/scripts/run_in_notebook.sh
# Stop:         docker exec notebook pkill -f "services\."
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
set -a; [ -f .env ] && . ./.env; set +a
export DATA_DIR=/home/ibm-user/shared/sepsis PYTHONPATH="$REPO" TORCHDYNAMO_DISABLE=1 PYTHONUNBUFFERED=1
export GRANITE_MODEL="$DATA_DIR/models/granite-4.0-h-350m-base-be.f16.gguf" GRANITE_THREADS=1
export GRANITE_URL=http://127.0.0.1:8080/note SCORER_URL=http://127.0.0.1:8000
python -m pip install -q fastapi uvicorn streamlit requests
mkdir -p "$DATA_DIR/runtime"
LOG="$DATA_DIR/runtime"
nohup python -m uvicorn services.granite.main:app --host 0.0.0.0 --port 8080 > "$LOG/granite.log" 2>&1 &
nohup python -m uvicorn services.scorer.main:app --host 0.0.0.0 --port 8000 > "$LOG/scorer.log" 2>&1 &
sleep 5
nohup python -m services.replayer.main > "$LOG/replayer.log" 2>&1 &
nohup python -m streamlit run services/dashboard/app.py --server.port=8501 --server.address=0.0.0.0 \
      --server.headless=true --browser.gatherUsageStats=false > "$LOG/dashboard.log" 2>&1 &
echo "Started. Logs in $LOG/*.log"
