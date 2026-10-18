"""Handoff-note facts, fact checking and template fallback for SepsisWatch Z.

Granite is a small *base* model: it writes fluent text, but it copies, loops and invents numbers.
So the scorer turns the alert into plain-language facts with units and normal ranges, Granite only
rewrites them as a short note, and every note is checked here before a nurse sees it.
"""
import difflib
import re

# base variable -> (display name, unit, low, high)   normal ranges are approximate adult ICU references
RANGES = {
    "HR": ("heart rate", "/min", 60, 100),
    "Resp": ("respiratory rate", "/min", 12, 20),
    "Temp": ("temperature", "°C", 36, 38),
    "MAP": ("mean arterial pressure", "mmHg", 65, None),
    "SBP": ("systolic BP", "mmHg", 90, None),
    "DBP": ("diastolic BP", "mmHg", 40, None),
    "O2Sat": ("O2 saturation", "%", 92, None),
    "Lactate": ("lactate", "mmol/L", None, 2),
    "WBC": ("white cell count", "x10^9/L", 4, 12),
    "Platelets": ("platelets", "x10^9/L", 150, None),
    "Creatinine": ("creatinine", "mg/dL", None, 1.2),
    "BUN": ("BUN", "mg/dL", None, 20),
    "Bilirubin_total": ("bilirubin", "mg/dL", None, 1.2),
    "Glucose": ("glucose", "mg/dL", 70, 180),
    "pH": ("pH", "", 7.35, 7.45),
    "HCO3": ("bicarbonate", "mmol/L", 22, None),
    "BaseExcess": ("base excess", "mmol/L", -2, None),
    "FiO2": ("FiO2", "", None, 0.4),
    "shock_index": ("shock index", "", None, 0.9),
}
FLAGS = {"high_lactate": "lactate above 2 mmol/L", "low_platelets": "platelets below 150 x10^9/L",
         "high_creatinine": "creatinine above 1.2 mg/dL", "high_bilirubin": "bilirubin above 1.2 mg/dL"}
VITAL_ORDER = ["Temp", "HR", "Resp", "MAP", "SBP", "O2Sat"]


def fmt(v: float) -> str:
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


def _status(base: str, v: float) -> str:
    _, _, lo, hi = RANGES[base]
    if lo is not None and v < lo:
        return "low"
    if hi is not None and v > hi:
        return "high"
    return "normal"


def phrase(feature: str, v) -> str | None:
    """One driver of the alert as a short clinical phrase, e.g. 'lowest MAP in 6 h 61 mmHg (low)'."""
    if feature in FLAGS:
        return FLAGS[feature] if v == 1 else None
    if v is None:
        return None
    if feature == "SIRS":
        return f"{fmt(v)} of 4 SIRS criteria met"
    if feature == "qSOFA":
        return f"qSOFA score {fmt(v)}"
    if feature == "BUN_creatinine_ratio":
        return f"BUN/creatinine ratio {fmt(v)}"
    base, _, stat = feature.partition("_6h_")
    if base not in RANGES:
        return f"{base} {fmt(v)}"
    name, unit, _, _ = RANGES[base]
    u = f" {unit}" if unit and unit != "%" else unit
    if stat == "change":
        if abs(v) < 0.5 and base != "Temp":
            return None
        return f"{name} {'up' if v > 0 else 'down'} {fmt(abs(v))}{u} in the last 6 h"
    st = _status(base, v)
    tag = "" if st == "normal" else f" ({st})"
    if stat == "mean":
        return f"{name} averaging {fmt(v)}{u} over 6 h{tag}"
    if stat == "min":
        return f"lowest {name} in 6 h {fmt(v)}{u}{tag}"
    if stat == "max":
        return f"highest {name} in 6 h {fmt(v)}{u}{tag}"
    return f"{name} {fmt(v)}{u}{tag}"


def build_facts(job: dict, risk_before: float | None) -> list[str]:
    """Facts for one Critical alert: risk trend, top model drivers, then other abnormal vitals."""
    risk = f"{round(100 * job['risk'])}%"
    if risk_before is not None and round(100 * risk_before) < round(100 * job["risk"]):
        trend = f"Sepsis risk score rose from {round(100 * risk_before)}% to {risk} in the last 6 h (Critical)"
    else:
        trend = f"Sepsis risk score {risk} (Critical)"
    facts = [trend, f"{job['icu_hours']} h in ICU"]
    seen = set()
    for d in job.get("drivers", []):
        p = phrase(d["feature"], d.get("value"))
        if p:
            facts.append(p)
            seen.add(d["feature"].split("_6h_")[0])
    for base in VITAL_ORDER:                          # current vitals out of range that the drivers did not cover
        v = (job.get("vitals") or {}).get(base)
        if base not in seen and v is not None and _status(base, v) != "normal" and len(facts) < 6:
            facts.append(phrase(base, v))
    return facts


def facts_text(facts: list[str]) -> str:
    return "\n".join(f"- {f}" for f in facts)


def template_note(bed, facts: list[str]) -> str:
    findings = "; ".join(facts[2:]) or "several vital signs changed"
    return (f"Bed {bed} ({facts[1]}): {facts[0][0].lower()}{facts[0][1:]}. Main findings: {findings}. "
            "Please reassess at the bedside and follow the unit's sepsis protocol.")


# ----------------------------------------------------------------------------- checking Granite's text
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
# a clinical topic may appear in the note only if the facts mention it (small models copy topics from examples)
TOPICS = {
    "lactate": ["lactate"], "heart": ["heart rate", "tachycard", "pulse"],
    "temperature": ["temperature", "fever", "febrile", "hypotherm"],
    "pressure": ["blood pressure", "arterial pressure", r"\bmap\b", "hypotens", "systolic", "diastolic", r"\bbp\b"],
    "breathing": ["respiratory", "breathing", "tachypn", "respiration"],
    "oxygen": ["o2", "oxygen", "saturation", "spo2", "fio2"], "platelets": ["platelet"],
    "kidney": ["creatinine", "kidney", "renal", r"\bbun\b", "urine"], "liver": ["bilirubin", "liver", "jaundice"],
    "white": ["white cell", r"\bwbc\b", "leukocyt"], "glucose": ["glucose"], "shock": ["shock index"],
    "drugs": ["antibiotic", "vasopressor", "noradrenaline", "norepinephrine", "fluid bolus", r"\bmg\b dose"],
}


def _mentions(text: str, pats) -> bool:
    return any(re.search(p if p.startswith(r"\b") else re.escape(p), text) for p in pats)


def clean_note(text: str) -> str:
    """Remove the classic small-model failures: repeated sentences, a cut-off last sentence, bed numbers."""
    text = re.sub(r"(?i)\bbed\s*\d+\b", "this patient", text)
    text = re.sub(r"\s+", " ", text).strip()
    sentences, out = re.split(r"(?<=[.!?])\s+", text), []
    for s in sentences:
        key = re.sub(r"\W+", " ", s.lower()).strip()
        if key and all(difflib.SequenceMatcher(None, key, re.sub(r"\W+", " ", o.lower())).ratio() < 0.8 for o in out):
            out.append(s)
    if out and not out[-1].endswith((".", "!", "?")):
        out = out[:-1]                                   # drop an unfinished sentence (max_tokens reached)
    return " ".join(out[:4])


def validate_note(raw: str, bed, facts: list[str], examples: list[str]):
    """Return (note, None) if the Granite text can be shown, else (None, reason)."""
    text = clean_note(raw)
    ftext = facts_text(facts).lower()
    if len(text) < 40:
        return None, "too short or looping"
    allowed = [float(x) for x in _NUM.findall(ftext)] + [6.0]
    for x in _NUM.findall(text):
        v = float(x)
        if not any(abs(v - a) <= max(0.6, 0.02 * abs(a)) for a in allowed):
            return None, f"number {x} not in the facts"
    low = text.lower()
    for topic, pats in TOPICS.items():
        if _mentions(low, pats) and not _mentions(ftext, pats):
            return None, f"mentions {topic}, which is not in the facts"
    for ex in examples:
        if difflib.SequenceMatcher(None, low, ex.lower()).ratio() > 0.7:
            return None, "copied an example note"
    return f"Bed {bed}: {text[0].upper()}{text[1:]}", None
