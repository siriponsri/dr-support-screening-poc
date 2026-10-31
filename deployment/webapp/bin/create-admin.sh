#!/bin/sh
# Create or reset one administrator account. The password is typed and never shown or stored in clear text.
# Usage: create-admin.sh <username>
set -eu
. "$(dirname "$0")/common.sh"
user=${1:?usage: create-admin.sh <username>}
printf 'New password for %s: ' "$user"
stty -echo 2>/dev/null || true; read -r password; stty echo 2>/dev/null || true; echo
printf '%s\n' "$password" | compose run --rm -T review python -m dr_support.services.pilot_auth set-user \
  --file /data/config/pilot-users.json --username "$user" --role admin --must-change
