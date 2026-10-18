# 🩺 SepsisWatch Z

**Early sepsis warning for the ICU, running entirely on an IBM z17 mainframe.**
Every patient, every hour: who to look at first, why, and a handoff note — without patient data ever leaving the machine.

`IBM Z Datathon 2026` · `Theme 1: Real-Time AI for Critical Decisions` · `Theme 2: AI Secured` · `Event code SSF2026`

🎬 **Demo video:** _add YouTube link here_ · 📊 **Pitch deck:** [`docs/SepsisWatchZ_pitch_deck.pdf`](docs/SepsisWatchZ_pitch_deck.pdf)

![SepsisWatch Z bed board running on the IBM z17](docs/figures/dashboard.png)

---

## 💡 The problem

- **Sepsis kills about 11 million people a year** — roughly 1 in 5 deaths worldwide — and every hour of delay matters.
- In the ICU its early signs are **subtle and scattered** across dozens of vital signs and lab values.
- Today's screening rule (**SIRS ≥ 2**) is so noisy that, on real data, it kept patients *without* sepsis **in alarm 24% of the time** → nurses stop trusting alarms.
- Health data is sensitive: hospitals can't simply send it to a public-cloud AI.

## ✅ Our solution

A live **ICU bed board** that scores every patient every hour and shows:

| | |
|---|---|
| 🔴 🟡 🟢 | **Critical / Watch / Stable** for each bed |
| 🔎 | **Why this alert** — the top clinical drivers (e.g. lactate, respiratory rate) |
| 📝 | A **handoff note** written by **IBM Granite** on the z17 and **fact-checked** before a nurse sees it |
| 🔒 | Patient IDs **tokenized**, age/sex **encrypted with CPACF**, every alert in a **tamper-evident audit log** |

> Decision support, not diagnosis — clinicians always decide.

## 📈 Results (on a hospital the model never saw)

We trained on hospital A and tested on hospital B from the public **PhysioNet 2019** dataset (40,336 real ICU stays, 1.55 M patient-hours).

| | Sepsis patients alerted (≤ 12 h before onset) | Time in alarm for patients *without* sepsis | New false alarms per patient-day |
|---|:---:|:---:|:---:|
| SIRS ≥ 2 (today) | 75% | 24% | 1.32 |
| **SepsisWatch Z** | **55%** | **8%** ⬇️ | **0.49** ⬇️ |

- **One third of the alarm time** and **63% fewer new false alarms** than SIRS.
- Tuned to SIRS-level detection (68%), it still spends **40% less time in alarm**.
- Consistent across groups: detection differs by 1.7 points between women and men.

⚡ **On the Telum II on-chip AI accelerator (NNPA):** a 12-bed ward is scored in **~1.5 ms**, and the whole test hospital (762 k patient-hours) **12× faster than on CPU** with **99.98% identical decisions**.

Full tables, fairness and figures → [`docs/results.md`](docs/results.md)

## 🏗️ How it works

![UML deployment and component diagram](docs/figures/architecture.png)

1. **Train** (5 Jupyter notebooks on the z17): ingest → 140 hourly features → XGBoost → neural network → evaluate.
2. **Stream**: a replayer sends a 12-bed ward to the **scorer** every clinical hour.
3. **Score**: XGBoost + a neural network **on the NNPA** → risk level + why.
4. **Explain**: when a patient turns Critical, **IBM Granite** (llama.cpp + zDNN) drafts a note; a **fact-checker** rejects anything not in the data.
5. **Show**: the dashboard reads the stored results — the nurse opens it through an SSH tunnel.

UML source: [`docs/architecture/`](docs/architecture/)

## 🖥️ IBM Z features we use

| IBM Z capability | What it does in SepsisWatch Z |
|---|---|
| **Telum II NNPA** (on-chip AI) | Runs the neural network that decides the alerts |
| **zDNN** | Runs IBM Granite locally for the handoff notes |
| **CPACF** (hardware crypto) | AES-256-GCM encryption of sensitive fields, SHA-3 audit chain |
| **SIMD vector units** | Fast XGBoost and data processing |
| **z/VM + containers** | 4 isolated Docker services on s390x, nothing exposed to the internet |

## 🚀 Run it (on the LinuxONE VM)

```bash
git clone https://github.com/HemsyCA/DATAIBMZOS-IBM-Z-Datathon-2026.git
cd DATAIBMZOS-IBM-Z-Datathon-2026
bash scripts/make_env.sh          # creates .env with keys (never committed)
docker compose up -d --build      # replayer · scorer · granite · dashboard
curl -s localhost:18000/health    # → "device": "nnpa", "encryption": true
```

Then open the dashboard through an SSH tunnel, e.g. `ssh -L 8501:localhost:8501 linux1@<vm-ip>` → http://localhost:8501 (port set by `DASHBOARD_HOST_PORT` in `.env`).
To rebuild the models, run `notebooks/01` → `05` in Jupyter Lab. Details: [`services/README.md`](services/README.md).

## 📁 What's inside

```
notebooks/        5 notebooks, executed on the IBM z17 (outputs included)
services/         scorer · replayer · granite · dashboard (FastAPI)
security/         tokens · encryption (CPACF) · hash-chained audit
docs/             results, figures, architecture, pitch deck
docs/evidence/    screenshots from the z17 + the 2 IBM labs
```

## 🧭 Responsible AI

- Alarm thresholds cap false alarms (≤ 1 per patient-day) to fight alarm fatigue.
- Explanations show physiology only; the LLM never receives patient identifiers.
- It outputs a **risk score**, not a diagnosis. Validated on a public 2019 benchmark — the next step is local validation with hospitals.

## 🧰 Built with

[PhysioNet 2019](https://physionet.org/content/challenge-2019/1.0.0/) · Python · NumPy · pandas · scikit-learn · XGBoost · PyTorch + IBM `torch_nnpa` · FastAPI · llama.cpp + zDNN · [IBM Granite 4.0](https://huggingface.co/ibm-granite) · OpenSSL · Docker

## 👥 Team

**Hemsy · Jhojan · Misael · Miguel** — built during the IBM Z Datathon, Oct 17–18, 2026.
