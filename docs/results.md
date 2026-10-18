# Results — SepsisWatch Z

Trained on hospital A (PhysioNet 2019 set A) and evaluated on hospital B (set B), which no model saw during training.
Thresholds chosen on validation (hospital A) with at most 1.0 false alarm per patient-day.
Detection = an alert within 12 h before sepsis onset. Alert = a new episode above the threshold.

## Hospital B

| model | AUROC_hourly | AUPRC_hourly | sensitivity | lead_time_median_h | false_alarms_per_day |
|---|---|---|---|---|---|
| SIRS ≥ 2 | 0.665 | 0.028 | 75.0% | 11.0 h | 1.32 |
| qSOFA ≥ 2 | 0.578 | 0.018 | 21.8% | 7.0 h | 0.35 |
| XGBoost | 0.776 | 0.056 | 88.6% | 11.5 h | 1.06 |
| NNPA network | 0.743 | 0.059 | 70.7% | 11.0 h | 0.85 |
| Ensemble | 0.782 | 0.065 | 74.8% | 11.0 h | 0.72 |

Hourly prevalence in hospital B: 0.0141.

## Fairness (Ensemble, hospital B)

| dimension | group | patients | sensitivity | lead_time_median_h | false_alarms_per_day |
|---|---|---|---|---|---|
| Sex | Female | 9268 | 74.9% | 11.0 h | 0.69 |
| Sex | Male | 10732 | 74.7% | 11.0 h | 0.75 |
| Age group | < 45 | 3387 | 76.5% | 11.0 h | 0.72 |
| Age group | 45–64 | 7709 | 73.3% | 11.0 h | 0.73 |
| Age group | 65–79 | 6582 | 76.2% | 12.0 h | 0.71 |
| Age group | ≥ 80 | 2322 | 72.9% | 11.0 h | 0.73 |

Figures: `docs/figures/results_hospital_B.png`, `docs/figures/fairness_hospital_B.png`, `docs/figures/xgb_importance.png`, `docs/figures/latency_cpu_vs_nnpa.png`.
