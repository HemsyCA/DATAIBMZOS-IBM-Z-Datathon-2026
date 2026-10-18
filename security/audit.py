"""Append-only audit log: each record stores the SHA3-256 hash of the previous one."""
import hashlib
import json
import os
import threading
from datetime import datetime, timezone

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
AUDIT_PATH = os.environ.get("AUDIT_PATH", f"{DATA_DIR}/audit/alerts.jsonl")
GENESIS = "0" * 64

_lock = threading.Lock()
_last_hash = None


def _tail_hash(path: str) -> str:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return GENESIS
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos, buf = f.tell(), b""
        while pos > 0 and buf.count(b"\n") < 2:
            step = min(4096, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
    last = buf.strip().split(b"\n")[-1]
    return json.loads(last)["hash"]


def record_hash(prev_hash: str, record: dict) -> str:
    payload = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha3_256((prev_hash + payload).encode()).hexdigest()


def append_alert(record: dict, path: str = AUDIT_PATH) -> dict:
    global _last_hash
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _lock:
        if _last_hash is None:
            _last_hash = _tail_hash(path)
        rec = dict(record)
        rec["ts"] = datetime.now(timezone.utc).isoformat()
        rec["prev_hash"] = _last_hash
        rec["hash"] = record_hash(_last_hash, rec)
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        _last_hash = rec["hash"]
    return rec
