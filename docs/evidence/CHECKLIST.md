# Evidence checklist — SepsisWatch Z (IBM Z Datathon 2026)

Each screenshot is saved in `docs/evidence/` with the number and name below. Mark `[x]` when done.
All screenshots must show **English** output.

## A. LinuxONE platform

- [x] `01-vm-s390x-ubuntu.png` — `uname -m` = s390x and Ubuntu 24.04 on the VM (Hemsy)
- [x] `02-docker-ok.png` — `docker run hello-world` on s390x (Hemsy)
- [x] `03-jupyter-container.png` — `notebook` container running (`docker ps`) (Hemsy)
- [x] `04-jupyter-lab.png` — Jupyter Lab with the IBM Z / LinuxONE image (Hemsy)
- [x] `05-ai-libraries.png` — numpy, pandas, sklearn, torch, tensorflow on s390x (Hemsy) · *re-run `00_environment_test.ipynb` and recapture if it shows Spanish*
- [x] `labs/` — the 2 mandatory IBM labs completed (Jhojan)

## B. Data and features

- [ ] `06-notebook-env-s390x-nnpa.png` — notebook 01, section 1: s390x, 3 CPUs, NNPA and vxe2 = True · *recapture in English*
- [ ] `07-ingest-z17.png` — notebook 01, section 4: 40,336 patients, 1,552,210 rows, total ingest time on s390x · *recapture in English*
- [ ] `08-features-z17.png` — notebook 02: train/val/test split table and "Total notebook time ... on s390x"

## C. IBM Z capabilities

- [ ] `09-z17-nnpa-flag.png` — `lscpu` (Machine type 9175) and `grep -o -w nnpa /proc/cpuinfo`
- [ ] `10-zvm-ifl.png` — `sudo vmcp q v all` showing the 3 IFL CPUs
- [ ] `11-tensor-nnpa.png` — notebook 04, section 6: `NNPA available: True` and "Evidence 11 → device: nnpa:0"
- [ ] `12-latency-cpu-vs-nnpa.png` — notebook 04, section 8: p50/p95 table and chart
- [ ] `13-cpacf-openssl.png` — `grep -E '^driver' /proc/crypto` (aes-s390) and `openssl speed -evp aes-256-gcm -seconds 3`
- [ ] `14-granite-zdnn.png` — Granite load log showing `libggml-zdnn.so`

## D. Services and security

- [ ] `15-docker-compose-ps.png` — `docker compose ps` with replayer, scorer, granite and dashboard up
- [ ] `16-audit-ok.png` — `verify_audit.py` passing (green)
- [ ] `17-audit-tampered.png` — `verify_audit.py` failing (red) after editing one record
- [ ] `18-apparmor.png` — `sudo aa-status`

## E. Model and results

- [ ] `19-xgb-importance.png` — notebook 03, section 7: top 20 features
- [ ] `20-metrics-hospital-b.png` — notebook 05, section 5: SIRS/qSOFA vs. XGBoost vs. NNPA network vs. ensemble
- [ ] `21-fairness.png` — notebook 05, section 7: sensitivity by sex and age group

## F. Product

- [ ] `22-dashboard-critical.png` — dashboard with a Critical patient and its Granite note
- [ ] `23-github-repo.png` — public repository with README

## Before submitting

- [ ] Repository set to **public**
- [ ] All screenshots committed and referenced in the README / deck
