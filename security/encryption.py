"""AES-256-GCM field encryption through OpenSSL, which uses CPACF hardware crypto on IBM Z.

`cryptography` has no pip wheel for s390x, so when it is missing we call OpenSSL's libcrypto
(already present for Python's ssl module) directly with ctypes: EVP_aes_256_gcm runs on CPACF.
Output format (both backends): hex(nonce[12] + ciphertext + tag[16]).
If neither backend is available, AVAILABLE is False and encrypt() returns None (never plaintext).
"""
import ctypes
import ctypes.util
import glob
import os

BACKEND = None
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    BACKEND = "cryptography"
except Exception:  # pragma: no cover - depends on the image
    AESGCM = None


def _load_libcrypto():
    names = [ctypes.util.find_library("crypto"), "libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so"]
    for pattern in ("/usr/lib*/libcrypto.so*", "/usr/lib/*/libcrypto.so*", "/lib*/libcrypto.so*",
                    "/opt/venv/lib*/**/libcrypto*.so*", "/opt/conda/lib/libcrypto.so*"):
        names += sorted(glob.glob(pattern, recursive=True))
    for name in names:
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            lib.EVP_aes_256_gcm  # noqa: B018  (symbol check)
            return lib
        except (OSError, AttributeError):
            continue
    return None


_lib = None
if BACKEND is None:
    _lib = _load_libcrypto()
    if _lib is not None:
        vp, ip, cp = ctypes.c_void_p, ctypes.c_int, ctypes.c_char_p
        _lib.EVP_CIPHER_CTX_new.restype = vp
        _lib.EVP_CIPHER_CTX_free.argtypes = [vp]
        _lib.EVP_aes_256_gcm.restype = vp
        for fn in ("EVP_EncryptInit_ex", "EVP_DecryptInit_ex"):
            getattr(_lib, fn).argtypes = [vp, vp, vp, cp, cp]
        for fn in ("EVP_EncryptUpdate", "EVP_DecryptUpdate"):
            getattr(_lib, fn).argtypes = [vp, cp, ctypes.POINTER(ip), cp, ip]
        for fn in ("EVP_EncryptFinal_ex", "EVP_DecryptFinal_ex"):
            getattr(_lib, fn).argtypes = [vp, cp, ctypes.POINTER(ip)]
        _lib.EVP_CIPHER_CTX_ctrl.argtypes = [vp, ip, ip, vp]
        BACKEND = "openssl-libcrypto"

AVAILABLE = BACKEND is not None
_SET_IVLEN, _GET_TAG, _SET_TAG = 0x9, 0x10, 0x11


def _key() -> bytes:
    key = bytes.fromhex(os.environ.get("SEPSIS_AES_KEY_HEX", ""))
    if len(key) != 32:
        raise RuntimeError("SEPSIS_AES_KEY_HEX must be 64 hex chars (32 bytes): run scripts/make_env.sh")
    return key


def _ossl_encrypt(key: bytes, nonce: bytes, pt: bytes) -> bytes:
    ctx = _lib.EVP_CIPHER_CTX_new()
    try:
        out, n, n2 = ctypes.create_string_buffer(len(pt) + 16), ctypes.c_int(0), ctypes.c_int(0)
        tag = ctypes.create_string_buffer(16)
        ok = (_lib.EVP_EncryptInit_ex(ctx, _lib.EVP_aes_256_gcm(), None, None, None)
              and _lib.EVP_CIPHER_CTX_ctrl(ctx, _SET_IVLEN, len(nonce), None)
              and _lib.EVP_EncryptInit_ex(ctx, None, None, key, nonce)
              and _lib.EVP_EncryptUpdate(ctx, out, ctypes.byref(n), pt, len(pt))
              and _lib.EVP_EncryptFinal_ex(ctx, ctypes.cast(ctypes.addressof(out) + n.value, ctypes.c_char_p), ctypes.byref(n2))
              and _lib.EVP_CIPHER_CTX_ctrl(ctx, _GET_TAG, 16, tag))
        if not ok:
            raise RuntimeError("OpenSSL AES-GCM encryption failed")
        return out.raw[: n.value + n2.value] + tag.raw
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def _ossl_decrypt(key: bytes, nonce: bytes, ct_tag: bytes) -> bytes:
    ct, tag = ct_tag[:-16], ct_tag[-16:]
    ctx = _lib.EVP_CIPHER_CTX_new()
    try:
        out, n, n2 = ctypes.create_string_buffer(len(ct) + 16), ctypes.c_int(0), ctypes.c_int(0)
        tagbuf = ctypes.create_string_buffer(tag, 16)
        ok = (_lib.EVP_DecryptInit_ex(ctx, _lib.EVP_aes_256_gcm(), None, None, None)
              and _lib.EVP_CIPHER_CTX_ctrl(ctx, _SET_IVLEN, len(nonce), None)
              and _lib.EVP_DecryptInit_ex(ctx, None, None, key, nonce)
              and _lib.EVP_DecryptUpdate(ctx, out, ctypes.byref(n), ct, len(ct))
              and _lib.EVP_CIPHER_CTX_ctrl(ctx, _SET_TAG, 16, tagbuf))
        if not ok or _lib.EVP_DecryptFinal_ex(ctx, ctypes.cast(ctypes.addressof(out) + n.value, ctypes.c_char_p), ctypes.byref(n2)) <= 0:
            raise ValueError("authentication failed (wrong key or tampered data)")
        return out.raw[: n.value + n2.value]
    finally:
        _lib.EVP_CIPHER_CTX_free(ctx)


def encrypt(plaintext) -> str | None:
    if not AVAILABLE or plaintext is None:
        return None
    key, nonce, pt = _key(), os.urandom(12), str(plaintext).encode()
    ct = AESGCM(key).encrypt(nonce, pt, None) if BACKEND == "cryptography" else _ossl_encrypt(key, nonce, pt)
    return (nonce + ct).hex()


def decrypt(blob_hex: str) -> str:
    raw = bytes.fromhex(blob_hex)
    key, nonce, ct = _key(), raw[:12], raw[12:]
    pt = AESGCM(key).decrypt(nonce, ct, None) if BACKEND == "cryptography" else _ossl_decrypt(key, nonce, ct)
    return pt.decode()
