import json, hashlib, os
from datetime import datetime, timezone

AUDIT_PATH = os.environ.get("AUDIT_PATH", "/data/audit.jsonl")

def append_alert(record: dict) -> dict:
    prev_hash = "0" * 64
    if os.path.exists(AUDIT_PATH):
        with open(AUDIT_PATH) as f:
            lines = f.read().splitlines()
        if lines:
            prev_hash = json.loads(lines[-1])["hash"]
    record = dict(record)
    record["ts"] = datetime.now(timezone.utc).isoformat()
    record["prev_hash"] = prev_hash
    payload = json.dumps(record, sort_keys=True, default=str)
    record["hash"] = hashlib.sha3_256((prev_hash + payload).encode()).hexdigest()
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
