# SepsisWatch Z — Early sepsis warning on IBM LinuxONE

**IBM Z Datathon 2026 · Theme: Real-Time AI for Critical Decisions (with AI Secured elements)**

SepsisWatch Z scores every ICU patient every hour and warns nurses which patients are likely to develop sepsis up to 6 hours before onset. Everything runs on an IBM LinuxONE (z17) virtual machine, so patient data never leaves the platform.

- **Who it is for:** ICU nurses and physicians, especially in hospitals with few specialists.
- **What they see:** a bed board with three levels (**Critical**, **Watch**, **Stable**) and, for each Critical patient, a short handoff note written by IBM Granite.
- **Decision support, not diagnosis:** the system tells the team where to look first. Clinicians always decide.

## How it uses IBM Z

| Component | IBM Z capability |
|---|---|
| Neural network inference | Telum II on-chip AI accelerator (**NNPA**) via `torch_nnpa` |
| XGBoost | z17 SIMD vector units (`vxe2`) |
| Granite handoff notes | `llama.cpp` built with **zDNN** |
| Security layer | **CPACF** hardware crypto (AES-256-GCM, SHA-3) |
| Whole system | Containers on s390x under z/VM, AppArmor |

## Data

[PhysioNet Computing in Cardiology Challenge 2019](https://physionet.org/content/challenge-2019/1.0.0/) (CC BY 4.0): 40,336 real ICU stays from two US hospital systems, one row per patient-hour, 40 clinical variables and a `SepsisLabel` that turns on 6 hours before Sepsis-3 onset.

We **train on hospital A (set A)** and **test on hospital B (set B)**, which the models never see during training. This shows the model generalizes across hospitals.

Data lives **outside the repo**, on the VM: `~/shared/sepsis/data/` (raw `.psv` files and processed pickles) and `~/shared/sepsis/models/` (trained models and predictions).

## Pipeline (run on the VM, in this order)

| Notebook | What it does | Main outputs |
|---|---|---|
| `notebooks/01_ingest_exploration.ipynb` | Merges the 40,336 `.psv` files into one table and explores the data | `sepsis_all.pkl`, `docs/figures/01–03_*.png` |
| `notebooks/02_features.ipynb` | 140 hourly features (last value, measured flags, 6 h trends, SIRS/qSOFA) and the A/B split | `features.pkl`, `feature_list.json` |
| `notebooks/03_xgboost.ipynb` | SIRS/qSOFA baselines and XGBoost, feature importance | `xgb.json`, `preds_xgb.pkl`, `docs/figures/xgb_importance.png` |
| `notebooks/04_nnpa_mlp.ipynb` | MLP trained on CPU, inference on the NNPA, CPU vs. NNPA latency benchmark | `mlp.pt`, `preds_mlp.pkl`, `docs/figures/latency_cpu_vs_nnpa.png` |
| `notebooks/05_eval.ipynb` | Ensemble, alert thresholds, patient-level metrics and fairness on hospital B | `thresholds.json`, `docs/results.md`, `docs/figures/*_hospital_B.png` |

Open each notebook in Jupyter Lab on the VM and use **Kernel → Restart Kernel and Run All Cells**. Results are in [`docs/results.md`](docs/results.md).

To download the dataset again: `bash data/download_physionet.sh` (about 7 minutes from the public S3 bucket).

## Repository layout

```
├── README.md
├── requirements.txt
├── data/download_physionet.sh      # dataset download (data itself stays outside the repo)
├── notebooks/                      # 01–05 pipeline, executed on the z17 with outputs saved
├── services/                       # scorer, replayer, granite, dashboard (see services/README.md)
└── docs/
    ├── figures/                    # charts for the deck and README
    ├── evidence/                   # screenshots for the judges + CHECKLIST.md + IBM labs
    └── results.md                  # final metrics (written by 05_eval)
```

## Team workflow

1. **Work on your laptop in a branch** named after you: `jhojan/...`, `miguel/...`, `hemsy/...`, `misael/...`. Open a Pull Request to `main` and merge it.
2. **The VM always stays on `main`.** It is a single shared folder used by everyone (same `linux1` user), so never switch branches there. To get the latest code:
   ```bash
   cd ~/shared/DATAIBMZOS-IBM-Z-Datathon-2026
   git checkout main && git pull
   ```
3. **Notebooks run on the VM, so their outputs are committed from the VM** right after running them, with your name:
   ```bash
   git add notebooks/0X_name.ipynb docs/figures docs/results.md
   git commit -m "Run 0X on z17" --author="Your Name <your-email>"
   git push
   ```
4. **One owner per notebook at a time.** `.ipynb` files produce messy merge conflicts. Pull before you edit a notebook that was run on the VM.
5. **Everything in English**: code, outputs, figures and screenshots (they are evidence for the judges).
6. Never delete files in `~/shared` or close other people's sessions without asking.

## Open-source libraries

NumPy, pandas, scikit-learn, XGBoost, PyTorch (with IBM `torch_nnpa`), Matplotlib, FastAPI, Uvicorn, Streamlit, llama.cpp, IBM Granite. See `requirements.txt`.

## Responsible AI

- Thresholds are capped at about one false alarm per patient-day to avoid alarm fatigue.
- Sensitivity is reported by sex and age group (`05_eval`).
- Patient IDs are tokenized and sensitive fields encrypted before storage; every alert goes to a hash-chained audit log.
- Limitation: validated on a public 2019 benchmark. Next step before clinical use: local validation with each hospital's own data.

## Team

Hemsy, Jhojan, Misael and Miguel.
