# Results — SepsisWatch Z

Trained on hospital A (PhysioNet 2019 set A) and evaluated on hospital B (set B), which no model saw during training.
Thresholds chosen on validation (hospital A): Critical allows at most 1.0 new false alarm per patient-day **and**
at most 10% of non-sepsis patient-hours in alarm. Detection = an alert within 12 h before sepsis onset.
Best model on validation (used by the dashboard): **NNPA network**.

## Hospital B

| model | AUROC_hourly | AUPRC_hourly | sensitivity | lead_time_median_h | false_alarms_per_day | alarm_hours |
|---|---|---|---|---|---|---|
| SIRS ≥ 2 | 0.665 | 0.028 | 75.0% | 11.0 h | 1.32 | 24.4% |
| qSOFA ≥ 2 | 0.578 | 0.018 | 21.8% | 7.0 h | 0.35 | 2.7% |
| XGBoost | 0.746 | 0.049 | 22.8% | 6.0 h | 0.09 | 1.4% |
| NNPA network | 0.711 | 0.046 | 55.0% | 11.0 h | 0.49 | 8.0% |
| Ensemble | 0.747 | 0.054 | 41.9% | 10.0 h | 0.20 | 3.4% |

Hourly prevalence in hospital B: 0.0141. *Alarm hours* = share of non-sepsis patient-hours spent in alarm.

## Same sensitivity as SIRS (threshold matched on validation)

| model | sensitivity | false_alarms_per_day | alarm_hours |
|---|---|---|---|
| XGBoost | 40.7% | 0.25 | 4.0% |
| NNPA network | 67.7% | 0.85 | 14.6% |
| Ensemble | 55.3% | 0.41 | 7.4% |
| SIRS ≥ 2 | 75.0% | 1.32 | 24.4% |

## Fairness (NNPA network, hospital B)

| dimension | group | patients | sensitivity | lead_time_median_h | false_alarms_per_day | alarm_hours |
|---|---|---|---|---|---|---|
| Sex | Female | 9268 | 56.0% | 11.0 h | 0.46 | 7.2% |
| Sex | Male | 10732 | 54.3% | 11.0 h | 0.52 | 8.8% |
| Age group | < 45 | 3387 | 54.5% | 11.0 h | 0.54 | 9.5% |
| Age group | 45–64 | 7709 | 53.2% | 11.0 h | 0.49 | 8.0% |
| Age group | 65–79 | 6582 | 58.5% | 11.0 h | 0.48 | 7.7% |
| Age group | ≥ 80 | 2322 | 51.2% | 11.0 h | 0.44 | 6.9% |

Figures: `docs/figures/results_hospital_B.png`, `docs/figures/fairness_hospital_B.png`, `docs/figures/xgb_importance.png`, `docs/figures/latency_cpu_vs_nnpa.png`.
