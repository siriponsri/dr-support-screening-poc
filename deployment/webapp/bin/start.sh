#!/bin/sh
# Start (or update to the loaded images) and wait until the web app answers.
set -eu
. "$(dirname "$0")/common.sh"
set -a; . "$ENV_FILE"; set +a
for d in config state output; do mkdir -p "${DR_DATA_DIR:-$PKG_DIR/data}/$d"; done
compose up -d
i=0
until compose exec -T review python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" >/dev/null 2>&1; do
  i=$((i + 1)); [ $i -lt 60 ] || { echo "The web app did not answer in 3 minutes; see: docker compose logs review"; exit 1; }
  sleep 3
done
echo "Ready: https://${DR_SITE_ADDRESS:-localhost}/app/"
