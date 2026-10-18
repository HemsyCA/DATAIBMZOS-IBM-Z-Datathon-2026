#!/usr/bin/env bash
# Creates .env (git-ignored) with fresh secrets and the IBM base image used by the notebook container.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists; delete it first if you want new keys (old tokens/encrypted fields would no longer match)."
  exit 0
fi

BASE_IMAGE=$(docker inspect notebook --format '{{.Config.Image}}' 2>/dev/null || true)
BASE_IMAGE=${BASE_IMAGE:-registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest}

cat > .env <<EOF
BASE_IMAGE=${BASE_IMAGE}
SHARED_DIR=${HOME}/shared
UID_GID=$(id -u):$(id -g)
DATA_DIR=/data/sepsis
SEPSIS_HMAC_KEY=$(openssl rand -hex 32)
SEPSIS_AES_KEY_HEX=$(openssl rand -hex 32)
EOF
chmod 600 .env
echo "Created .env (base image: ${BASE_IMAGE})"
