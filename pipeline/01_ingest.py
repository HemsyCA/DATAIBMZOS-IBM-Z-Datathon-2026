"""
01_ingest.py - Consolida los 40,336 archivos .psv de PhysioNet 2019 en una sola tabla.

Entrada : ~/shared/sepsis/data/raw/training_setA/*.psv  (hospital A)
          ~/shared/sepsis/data/raw/training_setB/*.psv  (hospital B)
Salida  : ~/shared/sepsis/data/processed/sepsis_all.pkl  (pandas, float32)

Columnas agregadas: patient_id (del nombre del archivo), hospital (A/B, de la carpeta)
y hour (0, 1, 2... dentro de cada paciente).

Nota: pyarrow/duckdb no tienen wheels para s390x en pip, por eso se usa pickle de pandas.

Uso (dentro del contenedor de Jupyter o la terminal de Jupyter):
    python pipeline/01_ingest.py
"""
import glob
import os
import platform
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

BASE = os.path.expanduser(os.environ.get("SEPSIS_DATA", "~/shared/sepsis/data"))
RAW = os.path.join(BASE, "raw")
OUT_DIR = os.path.join(BASE, "processed")
OUT_FILE = os.path.join(OUT_DIR, "sepsis_all.pkl")

# Las 41 columnas en el orden original del dataset
COLUMNS = [
    "HR", "O2Sat", "Temp", "SBP", "MAP", "DBP", "Resp", "EtCO2",
    "BaseExcess", "HCO3", "FiO2", "pH", "PaCO2", "SaO2", "AST", "BUN",
    "Alkalinephos", "Calcium", "Chloride", "Creatinine", "Bilirubin_direct",
    "Glucose", "Lactate", "Magnesium", "Phosphate", "Potassium",
    "Bilirubin_total", "TroponinI", "Hct", "Hgb", "PTT", "WBC",
    "Fibrinogen", "Platelets",
    "Age", "Gender", "Unit1", "Unit2", "HospAdmTime", "ICULOS",
    "SepsisLabel",
]


def read_patient(path):
    """Lee un .psv y le agrega patient_id, hospital y hour."""
    df = pd.read_csv(path, sep="|", dtype=np.float32)
    if list(df.columns) != COLUMNS:
        raise ValueError(f"Columnas inesperadas en {path}")
    df.insert(0, "patient_id", os.path.basename(path)[:-4])  # p000001.psv -> p000001
    df.insert(1, "hospital", "A" if "training_setA" in path else "B")
    df.insert(2, "hour", np.arange(len(df), dtype=np.int16))
    return df


def main():
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(RAW, "training_set*", "*.psv")))
    print(f"Maquina: {platform.machine()} | CPUs: {os.cpu_count()}")
    print(f"Archivos encontrados: {len(files):,}")

    # Leer en paralelo con todos los CPUs de la VM
    with Pool(os.cpu_count()) as pool:
        frames = pool.map(read_patient, files, chunksize=500)
    t_read = time.time() - t0

    df = pd.concat(frames, ignore_index=True)
    df["patient_id"] = df["patient_id"].astype("category")
    df["hospital"] = df["hospital"].astype("category")
    df["SepsisLabel"] = df["SepsisLabel"].astype(np.int8)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_pickle(OUT_FILE)
    t_total = time.time() - t0

    # Resumen para revisar y para el pitch
    per_patient = df.groupby("patient_id", observed=True).agg(
        hospital=("hospital", "first"),
        hours=("hour", "size"),
        sepsis=("SepsisLabel", "max"),
    )
    print(f"\nFilas (horas-paciente): {len(df):,} | Columnas: {df.shape[1]}")
    print(f"Memoria en RAM: {df.memory_usage(deep=True).sum() / 1024**2:,.0f} MB")
    print(f"Archivo: {OUT_FILE} ({os.path.getsize(OUT_FILE) / 1024**2:,.0f} MB)")
    print("\nPor hospital:")
    summary = per_patient.groupby("hospital", observed=True).agg(
        pacientes=("sepsis", "size"),
        con_sepsis=("sepsis", "sum"),
        horas_mediana=("hours", "median"),
    )
    summary["pct_sepsis"] = (100 * summary["con_sepsis"] / summary["pacientes"]).round(2)
    print(summary.to_string())
    print(f"\nTiempo lectura: {t_read:.1f} s | Tiempo total: {t_total:.1f} s (en {platform.machine()})")


if __name__ == "__main__":
    main()
