#!/bin/sh
# Stop all services of the hospital server. Database volume and folders are kept.
set -eu
PKG=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
set -a; . "$ENV_FILE"; set +a
docker compose -f "$PKG/../dual-mode/compose.yml" -f "$PKG/compose.override.yml" --profile "$DUAL_MODE_GPU_PROFILE" \
  --env-file "$ENV_FILE" stop
echo "Stopped. Data is kept."
