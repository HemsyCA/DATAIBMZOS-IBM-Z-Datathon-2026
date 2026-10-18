import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY = bytes.fromhex(os.environ["SEPSIS_AES_KEY_HEX"])  # 32 bytes

def encrypt(plaintext: str) -> str:
    aes = AESGCM(KEY)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()

def decrypt(blob_hex: str) -> str:
    raw = bytes.fromhex(blob_hex)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(KEY).decrypt(nonce, ct, None).decode()
