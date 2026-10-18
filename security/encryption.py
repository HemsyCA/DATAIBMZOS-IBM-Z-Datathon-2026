"""AES-256-GCM field encryption. OpenSSL uses CPACF hardware crypto on IBM Z.

`cryptography` has no pip wheel for s390x. If it is not installed, AVAILABLE is False and
encrypt() returns None, so callers must store nothing instead of plaintext.
"""
import os

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    AVAILABLE = True
except Exception:  # pragma: no cover - depends on the image
    AESGCM = None
    AVAILABLE = False


def _key() -> bytes:
    key = bytes.fromhex(os.environ.get("SEPSIS_AES_KEY_HEX", ""))
    if len(key) != 32:
        raise RuntimeError("SEPSIS_AES_KEY_HEX must be 64 hex chars (32 bytes): run scripts/make_env.sh")
    return key


def encrypt(plaintext) -> str | None:
    if not AVAILABLE:
        return None
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, str(plaintext).encode(), None)
    return (nonce + ct).hex()


def decrypt(blob_hex: str) -> str:
    raw = bytes.fromhex(blob_hex)
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode()
