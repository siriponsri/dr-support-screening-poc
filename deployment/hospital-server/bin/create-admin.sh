#!/bin/sh
# Create or reset one administrator account (password typed, never shown or stored in clear text).
# Usage: create-admin.sh <username>
set -eu
export MSYS_NO_PATHCONV=1
PKG=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
set -a; . "$ENV_FILE"; set +a
user=${1:?usage: create-admin.sh <username>}
printf 'New password for %s: ' "$user"
stty -echo 2>/dev/null || true; read -r password; stty echo 2>/dev/null || true; echo
printf '%s\n' "$password" | docker compose -f "$PKG/../dual-mode/compose.yml" -f "$PKG/compose.override.yml" \
  --profile "$DUAL_MODE_GPU_PROFILE" --env-file "$ENV_FILE" run --rm -T --no-deps review \
  python -m dr_support.services.pilot_auth set-user --file /data/config/pilot-users.json \
  --username "$user" --role admin --must-change
