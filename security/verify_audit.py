"""Verify the SHA3-256 hash chain of the audit log. Exit code 0 = intact, 1 = tampered.

Usage: python security/verify_audit.py [path]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from security.audit import AUDIT_PATH, GENESIS, record_hash  # noqa: E402

GREEN, RED, RESET = "\033[92m", "\033[91m", "\033[0m"


def verify(path: str = AUDIT_PATH) -> int:
    if not os.path.exists(path):
        print(f"{RED}FAIL: audit log not found at {path}{RESET}")
        return 1
    prev, n = GENESIS, 0
    with open(path) as f:
        for n, line in enumerate(f, start=1):
            rec = json.loads(line)
            stored = rec.pop("hash")
            if rec.get("prev_hash") != prev:
                print(f"{RED}FAIL: record {n} does not link to record {n - 1} (chain broken){RESET}")
                return 1
            if record_hash(prev, rec) != stored:
                print(f"{RED}FAIL: record {n} was modified (hash mismatch){RESET}")
                return 1
            prev = stored
    print(f"{GREEN}OK: {n:,} audit records verified, SHA3-256 hash chain intact ({path}){RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(verify(sys.argv[1] if len(sys.argv) > 1 else AUDIT_PATH))
