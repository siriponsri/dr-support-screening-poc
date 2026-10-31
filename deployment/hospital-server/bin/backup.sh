#!/bin/sh
# Database backup into $DR_DATA_DIR/backups; keeps the last 14. Add to cron for nightly runs, e.g.:
#   30 2 * * * DR_ENV_FILE=/etc/dr-screening/hospital.env /opt/dr-screening/deployment/hospital-server/bin/backup.sh
set -eu
PKG=$(cd "$(dirname "$0")/.." && pwd)
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
set -a; . "$ENV_FILE"; set +a
file="$DR_DATA_DIR/backups/dr_support-$(date +%Y%m%d-%H%M%S).dump"
docker compose -f "$PKG/../dual-mode/compose.yml" -f "$PKG/compose.override.yml" --profile "$DUAL_MODE_GPU_PROFILE" \
  --env-file "$ENV_FILE" exec -T postgres pg_dump -U "$DR_SUPPORT_POSTGRES_USER" -d "$DR_SUPPORT_POSTGRES_DB" -Fc > "$file"
[ -s "$file" ] || { echo "Backup is empty: $file"; exit 1; }
ls -1t "$DR_DATA_DIR"/backups/dr_support-*.dump | tail -n +15 | xargs -r rm -f
echo "Backup written: $file"
