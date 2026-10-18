# Checklist de evidencias — SepsisWatch Z (IBM Z Datathon 2026)

Cada captura se guarda en `docs/evidencias/` con el número y el nombre indicados.
Responsables según el plan del equipo. Marcar `[x]` al completar.

## A. Plataforma LinuxONE (listas)

- [x] `01-vm-s390x-ubuntu.png` — `uname -m` = s390x y Ubuntu 24.04 en la VM (Hemsy)
- [x] `02-docker-ok.png` — `docker run hello-world` en s390x (Hemsy)
- [x] `03-jupyter-container.png` — contenedor `notebook` arriba (`docker ps`) (Hemsy)
- [x] `04-jupyter-lab.png` — Jupyter Lab con imagen IBM Z / LinuxONE (Hemsy)
- [x] `05-librerias-ia.png` — numpy, pandas, sklearn, torch, tensorflow en s390x (Hemsy)
- [x] `labs/` — los 2 labs obligatorios de IBM completos (Jhojan)

## B. Datos y features (Hemsy)

- [x] `06-notebook-entorno-s390x-nnpa.png` — notebook 01, sección 1: s390x, 3 CPUs, NNPA y vxe2 = True
- [x] `07-ingesta-z17-61s.png` — notebook 01, sección 4: 40,336 pacientes, 1,552,210 filas, 61 s en s390x
- [ ] `08-features-z17.png` — notebook 02: tabla de división train/val/test y "Tiempo total ... en s390x"

## C. Capacidades de IBM Z

- [ ] `09-z17-nnpa-flag.png` — `lscpu` (Machine type 9175) y `grep -o -w nnpa /proc/cpuinfo` (Misael)
- [ ] `10-zvm-ifl.png` — `sudo vmcp q v all` con las 3 CPUs IFL (Misael)
- [ ] `11-tensor-nnpa.png` — `torch.nnpa.is_available()` = True y salida de la red en `nnpa:0` (Jhojan)
- [ ] `12-latencia-cpu-vs-nnpa.png` — tabla del benchmark p50/p95 CPU frente a NNPA (Jhojan)
- [ ] `13-cpacf-openssl.png` — `grep -E '^driver' /proc/crypto` (aes-s390) y `openssl speed -evp aes-256-gcm -seconds 3` (Misael)
- [ ] `14-granite-zdnn.png` — log de carga de Granite con `libggml-zdnn.so` (Misael)

## D. Servicios y seguridad (Misael)

- [ ] `15-docker-compose-ps.png` — `docker compose ps` con replayer, scorer, granite y dashboard arriba
- [ ] `16-auditoria-ok.png` — `verify_audit.py` en verde
- [ ] `17-auditoria-alterada.png` — `verify_audit.py` en rojo tras alterar un registro
- [ ] `18-apparmor.png` — `sudo aa-status`

## E. Modelo y resultados (Hemsy)

- [ ] `19-xgb-importancia.png` — variables que más pesan en XGBoost
- [ ] `20-metricas-hospital-b.png` — tabla final en hospital B: SIRS/qSOFA vs XGBoost vs red vs ensamble
- [ ] `21-equidad.png` — sensibilidad por sexo y grupo de edad

## F. Producto (Jhojan)

- [ ] `22-dashboard-critico.png` — tablero con un paciente en Crítico y su nota de Granite
- [ ] `23-github-repo.png` — repositorio público con README

## Antes de entregar

- [ ] Repositorio en **público**
- [ ] Todas las capturas subidas con commit y referenciadas en el README / deck
