"""IBM Granite handoff-note service (llama.cpp built with zDNN on IBM Z).

POST /note {"facts": "- fact\n- fact"} -> {"note": "...", "examples": [...]}
The input carries no identifiers: risk trend, hours in ICU and the alert drivers in plain words.
The model is a small *base* model, so it is guided with two fixed few-shot examples, a repeat penalty
and strict stop words. The prompt prefix never changes, so llama.cpp reuses its KV cache and only the
new facts are processed: notes come back in seconds on the z17. The scorer then fact-checks the note
(numbers, topics, high/low, invented history, copying, loops) and keeps the template if it fails.
"""
import os
import threading
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DATA_DIR = os.environ.get("DATA_DIR", "/data/sepsis")
MODEL_PATH = os.environ.get("GRANITE_MODEL", f"{DATA_DIR}/models/granite-4.0-h-350m-base-be.f16.gguf")
THREADS = int(os.environ.get("GRANITE_THREADS", "2"))

HEADER = ("Rewrite the facts as a short ICU nursing handoff note: 2 or 3 sentences of plain English, "
          "at most 60 words. Use only the facts. Do not add numbers, diagnoses or drugs.\n\n")

EXAMPLES = [
    ("- Sepsis risk score rose from 38% to 71% in the last 6 h (Critical)\n- 30 h in ICU\n"
     "- respiratory rate averaging 26.4 /min over 6 h (high)\n- heart rate 118 /min (high)\n- temperature 38.6 °C (high)",
     "Over the last 6 hours the sepsis risk score climbed from 38% to 71%. The patient is breathing fast at about "
     "26 per minute, heart rate is 118 and there is a fever of 38.6 °C. Please review at the bedside now and follow "
     "the unit's sepsis protocol."),
    ("- Sepsis risk score 64% (Critical)\n- 52 h in ICU\n- lowest mean arterial pressure in 6 h 61 mmHg (low)\n"
     "- lactate above 2 mmol/L\n- heart rate up 14 /min in the last 6 h",
     "Now Critical with a risk score of 64%. Blood pressure has dipped to a lowest MAP of 61 mmHg, lactate is above 2 "
     "and heart rate has climbed by 14 in six hours. A bedside assessment and the sepsis checklist are recommended."),
    ("- Sepsis risk score rose from 22% to 58% in the last 6 h (Critical)\n- 9 h in ICU\n"
     "- temperature 35.4 °C (low)\n- white cell count 15.2 x10^9/L (high)\n- O2 saturation 90% (low)",
     "Only 9 hours into the stay, the risk score has risen quickly to 58%. Temperature is low at 35.4 °C, white cells "
     "are raised at 15.2 and oxygen saturation is down to 90%. Please check the patient and escalate per local "
     "sepsis guidance."),
    ("- Sepsis risk score 83% (Critical)\n- 115 h in ICU\n- 3 of 4 SIRS criteria met\n"
     "- platelets below 150 x10^9/L\n- systolic BP 92 mmHg",
     "Risk score is high at 83% after 115 hours in the ICU. Three of the four SIRS criteria are met, platelets are "
     "below 150 and systolic pressure is 92. Consider a senior review and follow the sepsis protocol."),
]

app = FastAPI(title="SepsisWatch Z · Granite notes")
_llm, _lock, _load_lock = None, threading.Lock(), threading.Lock()


def llm():
    global _llm
    with _load_lock:          # the warm-up thread and the first request must not load the model twice
        if _llm is not None:
            return _llm
        from llama_cpp import Llama
        print("Loading Granite from", MODEL_PATH, flush=True)
        _llm = Llama(model_path=MODEL_PATH, n_ctx=1024, n_threads=THREADS, verbose=True)  # verbose: shows zDNN backend
        return _llm


def prompt(facts: str, shots) -> str:
    body = "".join(f"Facts:\n{f}\nNote: {n}\n\n" for f, n in shots)
    return HEADER + body + f"Facts:\n{facts}\nNote:"


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
    shots = EXAMPLES[:2]                       # fixed prefix -> llama.cpp reuses the cached prompt
    t0 = time.perf_counter()
    with _lock:   # one generation at a time on 3 vCPUs
        out = llm()(prompt(req.facts, shots), max_tokens=80, temperature=0.4, top_p=0.9, repeat_penalty=1.18,
                    stop=["\nFacts", "Facts:", "\n\n", "\n-", "Note:"], echo=False)
    text = out["choices"][0]["text"].strip()
    print(f"granite raw ({time.perf_counter() - t0:.1f}s):", text.replace("\n", " ")[:300], flush=True)
    if len(text) < 20:
        raise HTTPException(502, "empty note")
    return {"note": text, "examples": [n for _, n in shots]}
