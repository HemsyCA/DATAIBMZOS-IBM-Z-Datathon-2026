# Pitch numbers — SepsisWatch Z (verified)

Single source of truth for the deck, the video and the Hack2Skill form. Every number below was read from the
notebooks executed on the IBM z17 VM, from `docs/results.md`, or measured on the running services.
**If a number is not on this page, do not say it.**

## 1. The problem (external sources, see README)

| Number | Source |
|---|---|
| ~11 million sepsis deaths per year, about 1 in 5 deaths worldwide | WHO / Global Burden of Disease (2017 data, published 2020) |

## 2. Data (notebook 01)

| Number | Value |
|---|---|
| ICU stays | **40,336** patients (hospital A 20,336 · hospital B 20,000) |
| Patient-hours | **1,552,210** rows, 40 clinical variables |
| Patients who develop sepsis | **2,932 (7.3%)** · A 1,790 (8.8%) · B 1,142 (5.7%) |
| Median ICU stay / age | 38 h / 63 years |
| Missing data | heart rate 9.9% · temperature 66% · lactate 97% of hours |
| Signal before onset (24 h → 0 h) | heart rate 88 → 91 bpm (non-sepsis 84) · respiration 19.9 → 20.5 (non-sepsis 18.6) |

## 3. Method (notebooks 02–05)

- **139 hourly features** (last value, measured flags, hours since last measurement, 6 h trends, shock index, SIRS, qSOFA, organ-dysfunction flags). `ICULOS` removed to avoid a length-of-stay shortcut.
- **Train on hospital A, test on hospital B** (never seen in training). Split by patient, no leakage.
- Thresholds chosen on validation (hospital A): Critical ≤ 1 new false alarm per patient-day and ≤ 10% of non-sepsis hours in alarm.
- Detection = an alert within the 12 h before sepsis onset.

## 4. Results on hospital B (notebook 05, `docs/results.md`)

| Model | AUROC | AUPRC | Sensitivity | Median lead time | False alarms / patient-day | Non-sepsis hours in alarm |
|---|---|---|---|---|---|---|
| SIRS ≥ 2 (current practice) | 0.665 | 0.028 | 75.0% | 11 h | 1.32 | 24.4% |
| qSOFA ≥ 2 | 0.578 | 0.018 | 21.8% | 7 h | 0.35 | 2.7% |
| XGBoost | 0.746 | 0.049 | 22.8% | 6 h | 0.09 | 1.4% |
| **NNPA network (used by the dashboard)** | 0.711 | 0.046 | **55.0%** | **11 h** | **0.49** | **8.0%** |
| Ensemble | 0.747 | 0.054 | 41.9% | 10 h | 0.20 | 3.4% |

Hourly prevalence in hospital B: 1.4% (the AUPRC of a random model).

**Headline (NNPA network vs. SIRS):** alerts **55% of sepsis patients a median of 11 hours before onset**, with
**63% fewer false alarms per patient-day** (0.49 vs. 1.32) and **one third of the alarm time** (8% vs. 24% of non-sepsis hours).

**At SIRS-like sensitivity** (threshold matched on validation): 67.7% sensitivity with 14.6% of non-sepsis hours in alarm vs. 24.4% for SIRS → **40% less alarm time**.

**Fairness (NNPA network):** sensitivity 56.0% women vs. 54.3% men (gap 1.7 points); 51–59% across age groups (largest gap 7.4 points, ≥ 80 years lowest).

## 5. IBM Z (notebook 04, services, platform commands)

| Capability | Verified number |
|---|---|
| Machine | IBM **z17** (machine type 9175), 3 IFL CPUs under z/VM, 8 GB RAM |
| **NNPA (Telum II on-chip AI)** | Same quality as CPU (AUROC 0.711 both; 99.98% identical decisions) |
| NNPA speed — whole hospital B | 761,995 patient-hours scored in **0.22 s on NNPA vs. 2.73 s on CPU (12×)** |
| NNPA speed — batch of 4,096 | **0.85 ms vs. 14.4 ms on CPU (17×)**; peak **4.8 million patient-hours per second** |
| NNPA speed — one ward (12 beds) | 0.069 ms vs. 0.124 ms on CPU (1.8×) |
| Live service | 12-bed ward scored every clinical hour: MLP on NNPA ≈ 0.5 ms, full ward ≈ 1.6 ms |
| Ingest + features on z17 | 40,336 files merged in 60 s (3 CPUs in parallel); 140 features in 17 s |
| XGBoost | trained in 46 s; scores all hospital B in 1.3 s |
| **CPACF** (on-chip crypto) | AES-256-GCM via OpenSSL ≈ **15 GB/s**; kernel drivers `aes-s390` |
| Security | patient IDs → HMAC-SHA256 tokens; age/sex → AES-256-GCM (OpenSSL → CPACF); **30,000+ alerts** in a SHA3-256 hash-chained audit log, verified intact; tampering detected at the exact record |
| Granite (IBM, zDNN) | 350M model on llama.cpp with zDNN; ~12–15 s per handoff note; every note is fact-checked against the patient data and replaced by a safe template if it invents facts |
| Containers | 4 services (scorer, replayer, granite, dashboard) in Docker Compose; AppArmor enforcing |

## 6. Say it this way

- "Validated on PhysioNet 2019: 40,336 real ICU stays. Trained on one hospital system, tested on another it never saw."
- "SepsisWatch Z warns about 55% of sepsis patients a median of 11 hours before onset, with 63% fewer false alarms than SIRS."
- "On the Telum II AI accelerator, scoring a whole hospital takes 0.22 seconds instead of 2.7 — with the same accuracy."
- "Patient data never leaves the mainframe: tokenized, encrypted by CPACF hardware, and every alert is in a tamper-evident audit log."
- "Decision support, not diagnosis. Clinicians always decide."

## 7. Do NOT say

- "Detects all sepsis" or any sensitivity above 55% for the dashboard model (SIRS catches more cases: 75%).
- "Reduces deaths / losses by X%" — never measured.
- "Sub-millisecond" without context: true for the NNPA model on one ward (≈ 0.5 ms), not for the whole system.
- That Granite writes every note: most live notes are the fact-checked template while Granite runs (~12–15 s per note).
- Accuracy numbers: with 1.4% prevalence, accuracy is meaningless.
- That the model diagnoses or recommends treatment.

## 8. Limitations (for the last slide)

- Public 2019 benchmark (US hospitals); next step is local validation with each hospital's own data before clinical use.
- AUPRC is low in absolute terms (0.046 vs. 0.014 random) because sepsis hours are rare; the operational metrics (lead time, false alarms) are what clinicians feel.
- The model also uses measurement patterns (when tests were ordered); explanations shown to nurses use physiology only.
- ICU only; general wards (vitals every 4–8 h) are the next extension.
