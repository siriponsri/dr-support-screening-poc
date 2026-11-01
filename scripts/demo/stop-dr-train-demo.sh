#!/usr/bin/env bash
# Stops the demo web app started by start-dr-train-demo.sh.
# With --gateway it also stops the AI server on dr-train (it releases the GPU when idle anyway).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
PRIVATE=$(cygpath -u "${LOCALAPPDATA:-C:/Users/$USERNAME/AppData/Local}")/DRScreening/M1PrivateConfig
CONFIG=${DR_DEMO_CONFIG:-$PRIVATE/demo.env}
# shellcheck disable=SC1090
[ -f "$CONFIG" ] && . "$CONFIG"
PID_FILE="$PRIVATE/demo-logs/app.pid"
if [ -f "$PID_FILE" ] && kill "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Web app stopped."
else
  echo "The web app was not running."
fi
rm -f "$PID_FILE"
if [ "${1:-}" = "--gateway" ]; then
  if [ -z "${DR_HOST:-}" ] || [ -z "${DR_KEY:-}" ]; then
    echo "DR_HOST and DR_KEY must be set in $CONFIG to stop the AI server on dr-train."
    exit 1
  fi
  tr -d '\r' < "$HERE/remote-stop-gateway.sh" | ssh -i "$DR_KEY" \
      -o StrictHostKeyChecking=yes -o BatchMode=yes "$DR_HOST" 'sh -s'
fi
