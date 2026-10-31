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
  tr -d '\r' < "$HERE/remote-stop-gateway.sh" | ssh -i "${DR_KEY:-C:/Users/User/.ssh/id_ed25519_dr_train}" \
      -o StrictHostKeyChecking=yes -o BatchMode=yes "${DR_HOST:-siripon@100.77.149.83}" 'sh -s'
fi
