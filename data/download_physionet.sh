#!/usr/bin/env bash
# Downloads the PhysioNet Challenge 2019 dataset (40,336 .psv files) from the public S3 bucket.
# Usage: bash data/download_physionet.sh [target_folder]
set -euo pipefail

BASE="https://physionet-open.s3.amazonaws.com"
PREFIX="challenge-2019/1.0.0/training/"
OUT="${1:-$HOME/shared/sepsis/data/raw}"

mkdir -p "$OUT"
cd "$OUT"

# 1. List every file in the bucket (S3 returns 1000 keys per page)
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
echo "Files listed: $(wc -l < keys.txt)"

# 2. Download in parallel (32 at a time); files that already exist are skipped on re-runs
awk -v B="$BASE" -v P="$PREFIX" '{ print B "/" $0, substr($0, length(P) + 1) }' keys.txt \
  | xargs -n 2 -P 32 sh -c '[ -s "$2" ] || curl -s --retry 3 --create-dirs -o "$2" "$1"' _

echo "Downloaded setA: $(find training_setA -name '*.psv' | wc -l)"
echo "Downloaded setB: $(find training_setB -name '*.psv' | wc -l)"
du -sh "$OUT"
