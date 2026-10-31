#!/bin/sh
# Start the hospital local server (web app, PostgreSQL, gateway, three GPU model services, HTTPS front).
# Runs the dual-mode preflight first (GPU identity, verified read-only assets, private settings). No CPU fallback.
set -eu
PKG=$(cd "$(dirname "$0")/.." && pwd)
DUAL=$PKG/../dual-mode
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
[ -f "$ENV_FILE" ] || { echo "Settings file not found: $ENV_FILE"; exit 1; }
grep -v '^[[:space:]]*#' "$ENV_FILE" | grep -q 'REPLACE' && { echo "Settings file still has REPLACE values: $ENV_FILE"; exit 1; }
set -a; . "$ENV_FILE"; set +a
for d in config state output backups; do mkdir -p "$DR_DATA_DIR/$d"; done
"$DUAL/bin/preflight.sh"
docker compose -f "$DUAL/compose.yml" -f "$PKG/compose.override.yml" --profile "$DUAL_MODE_GPU_PROFILE" \
  --env-file "$ENV_FILE" up -d
echo "Started. Health: $PKG/bin/status.sh   Web: https://$DR_SITE_ADDRESS/app/"
