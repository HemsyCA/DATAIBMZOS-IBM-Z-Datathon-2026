import json, hashlib, sys, os

AUDIT_PATH = os.environ.get("AUDIT_PATH", "/data/audit.jsonl")

def verify(path=AUDIT_PATH):
    prev = "0" * 64
    with open(path) as f:
        for i, line in enumerate(f):
            rec = json.loads(line)
            stored_hash = rec.pop("hash")
            if rec.get("prev_hash") != prev:
                print(f"FAIL line {i+1}: prev_hash mismatch")
                return 1
            payload = json.dumps(rec, sort_keys=True, default=str)
            calc = hashlib.sha3_256((prev + payload).encode()).hexdigest()
            if calc != stored_hash:
                print(f"FAIL line {i+1}: hash mismatch")
                return 1
            prev = stored_hash
    print(f"OK: {i+1 if os.path.exists(path) else 0} records verified")
    return 0

if __name__ == "__main__":
    sys.exit(verify())
