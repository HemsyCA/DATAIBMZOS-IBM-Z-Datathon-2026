"""IBM Granite handoff-note service (llama.cpp built with zDNN on IBM Z).

POST /note {"facts": "..."} -> {"note": "..."}
Input carries no identifiers: hours in ICU, risk and the top clinical drivers only (the scorer adds the bed number and\nrejects any note with numbers that are not in the facts).
The model is a small *base* model, so it is guided with a fixed few-shot template.
"""
import os
import threading

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
MODEL_PATH = os.environ.get("GRANITE_MODEL", f"{DATA_DIR}/models/granite-4.0-h-350m-base-be.f16.gguf")
THREADS = int(os.environ.get("GRANITE_THREADS", "2"))

PROMPT = """Write a short, factual ICU nursing handoff note (max 60 words). Use only the numbers given in the facts. Do not diagnose. Do not prescribe drugs.

Facts: 30 h in ICU. Sepsis risk 0.71 (Critical). Respiratory rate (6 h mean) 26.4; Heart rate 118.0; Temperature 38.6.
Note: Sepsis risk is rising (Critical). Respiratory rate has averaged 26.4 over the last 6 hours, heart rate is 118 and temperature 38.6 °C. Please reassess at the bedside and follow the unit's sepsis protocol.

Facts: 52 h in ICU. Sepsis risk 0.64 (Critical). Mean arterial pressure (6 h min) 61.0; Lactate 3.1; Heart rate (6 h change) 14.0.
Note: Now Critical for sepsis risk. Mean arterial pressure dropped to 61, lactate is 3.1 and heart rate rose by 14 in 6 hours. Please reassess at the bedside and follow the unit's sepsis protocol.

Facts: {facts}
Note:"""

app = FastAPI(title="SepsisWatch Z · Granite notes")
_llm, _lock = None, threading.Lock()


def llm():
    global _llm
    if _llm is None:
        from llama_cpp import Llama
        print("Loading Granite from", MODEL_PATH, flush=True)
        _llm = Llama(model_path=MODEL_PATH, n_ctx=1024, n_threads=THREADS, verbose=True)  # verbose: shows zDNN backend
    return _llm


class Req(BaseModel):
    facts: str


@app.on_event("startup")
def warm():
    threading.Thread(target=lambda: llm(), daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "model": os.path.basename(MODEL_PATH), "loaded": _llm is not None}


@app.post("/note")
def note(req: Req):
    with _lock:   # one generation at a time on 3 vCPUs
        out = llm()(PROMPT.format(facts=req.facts), max_tokens=90, temperature=0.2,
                    stop=["\nFacts:", "\n\n"], echo=False)
    text = out["choices"][0]["text"].strip()
    if len(text) < 20:
        raise HTTPException(502, "empty note")
    return {"note": text}
