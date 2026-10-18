#!/usr/bin/env bash
# Descarga PhysioNet Challenge 2019 (40,336 archivos .psv) desde el bucket publico de S3.
# Uso: bash data/download_physionet.sh [carpeta_destino]
set -euo pipefail

BASE="https://physionet-open.s3.amazonaws.com"
PREFIX="challenge-2019/1.0.0/training/"
OUT="${1:-$HOME/shared/sepsis/data/raw}"

mkdir -p "$OUT"
cd "$OUT"

# 1. Listar todos los archivos del bucket (S3 devuelve 1000 por pagina)
: > keys.txt
MARKER=""
while :; do
  PAGE=$(curl -s --retry 3 "$BASE/?prefix=$PREFIX&max-keys=1000&marker=$MARKER")
  echo "$PAGE" | grep -oE "<Key>[^<]+\.psv</Key>" | sed -E 's#</?Key>##g' >> keys.txt
  if echo "$PAGE" | grep -q "<IsTruncated>true</IsTruncated>"; then
    MARKER=$(tail -n 1 keys.txt)
  else
    break
  fi
done
echo "Archivos listados: $(wc -l < keys.txt)"

# 2. Descargar en paralelo (32 a la vez); -z omite los que ya existen si se re-ejecuta
awk -v B="$BASE" -v P="$PREFIX" '{ print B "/" $0, substr($0, length(P) + 1) }' keys.txt \
  | xargs -n 2 -P 32 sh -c '[ -s "$2" ] || curl -s --retry 3 --create-dirs -o "$2" "$1"' _

echo "Descargados setA: $(find training_setA -name '*.psv' | wc -l)"
echo "Descargados setB: $(find training_setB -name '*.psv' | wc -l)"
du -sh "$OUT"
