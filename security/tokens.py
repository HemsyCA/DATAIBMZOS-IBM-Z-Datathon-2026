"""Patient ID -> irreversible HMAC-SHA256 token (the key never leaves the VM)."""
import hashlib
import hmac
import os


def _key() -> bytes:
    key = os.environ.get("SEPSIS_HMAC_KEY", "")
    if len(key) < 32:
        raise RuntimeError("SEPSIS_HMAC_KEY is missing or too short: run scripts/make_env.sh to create .env")
    return key.encode()


def patient_token(patient_id: str) -> str:
    return hmac.new(_key(), str(patient_id).encode(), hashlib.sha256).hexdigest()
