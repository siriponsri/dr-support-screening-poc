#!/bin/sh
# Show service health. No secret is printed.
set -eu
PKG=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
set -a; . "$ENV_FILE"; set +a
docker compose -f "$PKG/../dual-mode/compose.yml" -f "$PKG/compose.override.yml" --profile "$DUAL_MODE_GPU_PROFILE" \
  --env-file "$ENV_FILE" ps --format 'table {{.Service}}\t{{.State}}\t{{.Health}}'
nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv,noheader 2>/dev/null || true
