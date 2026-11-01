#!/bin/sh
# Nightly-safe database backup into a host folder (default ./data/backups). Keeps the last 14 files.
set -eu
. "$(dirname "$0")/common.sh"
set -a; . "$ENV_FILE"; set +a
dest=${DR_BACKUP_DIR:-${DR_DATA_DIR:-$PKG_DIR/data}/backups}
mkdir -p "$dest"
file="$dest/dr_support-$(date +%Y%m%d-%H%M%S).dump"
compose exec -T postgres pg_dump -U "$DR_SUPPORT_POSTGRES_USER" -d "$DR_SUPPORT_POSTGRES_DB" -Fc > "$file"
[ -s "$file" ] || { echo "Backup is empty: $file"; exit 1; }
ls -1t "$dest"/dr_support-*.dump | tail -n +15 | xargs -r rm -f
echo "Backup written: $file"
