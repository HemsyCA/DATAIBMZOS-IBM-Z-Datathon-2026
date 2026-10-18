import hmac, hashlib, os

KEY = os.environ["SEPSIS_HMAC_KEY"].encode()

def patient_token(patient_id: str) -> str:
    return hmac.new(KEY, patient_id.encode(), hashlib.sha256).hexdigest()
