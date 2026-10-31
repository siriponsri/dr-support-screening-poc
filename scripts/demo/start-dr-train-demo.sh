#!/usr/bin/env bash
# One click on the owner's workstation (Git Bash):
#   1. check the SSH route to dr-train (existing key, strict host key),
#   2. start the regular gateway there if it is not running (CPU only),
#   3. start the review web app here; it warms the GPU child (inside AI hours),
#   4. open the browser.
# Settings come from a private file (never in Git); see demo.env.example. No token is ever printed.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
PRIVATE=$(cygpath -u "${LOCALAPPDATA:-C:/Users/$USERNAME/AppData/Local}")/DRScreening/M1PrivateConfig
CONFIG=${DR_DEMO_CONFIG:-$PRIVATE/demo.env}

say() { printf '%s\n' "$*"; }
fail() { say ""; say "Stopped: $*"; exit 1; }

[ -f "$CONFIG" ] || fail "settings file not found ($CONFIG). Copy scripts/demo/demo.env.example there and fill it in."
# shellcheck disable=SC1090
. "$CONFIG"

DR_HOST=${DR_HOST:-siripon@100.77.149.83}
DR_KEY=${DR_KEY:-C:/Users/User/.ssh/id_ed25519_dr_train}
DR_APP_PORT=${DR_APP_PORT:-8010}
DR_MODEL_PORT=${DR_MODEL_PORT:-47860}
DR_IMAGES=${DR_IMAGES:-workspace}
PY=${DR_PYTHON:-$REPO/.venv/Scripts/python.exe}
for name in DR_DEPLOY DR_PINS_REMOTE DR_STATE DR_PINS_LOCAL DR_WORKSPACE DR_WORKSTATION; do
  [ -n "${!name:-}" ] || fail "$name is not set in $CONFIG"
done
[ -x "$PY" ] || fail "Python environment not found at $PY"
SSH=(ssh -i "$DR_KEY" -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=15 "$DR_HOST")
APP_URL="http://127.0.0.1:$DR_APP_PORT/app/"

say "DR Screening demo: starting"
say ""

if curl -s -o /dev/null -m 3 "http://127.0.0.1:$DR_APP_PORT/health"; then
  say "The web app is already running. Opening the browser."
  cmd.exe /c start "" "$APP_URL" >/dev/null 2>&1
  exit 0
fi

minutes=$("$PY" -c "from datetime import datetime, timedelta, timezone; t = datetime.now(timezone(timedelta(hours=7))); print(t.hour * 60 + t.minute)")
if [ "$minutes" -lt 360 ] || [ "$minutes" -ge 1315 ]; then
  fail "AI hours are 06:00 to 21:55 Thai time. The AI server only starts inside those hours."
fi

say "1/4 Checking the connection to dr-train"
"${SSH[@]}" true || fail "cannot reach dr-train over SSH. Check the network or VPN."

say "2/4 Starting the AI server on dr-train (if it is not running)"
result=$("${SSH[@]}" "sh -s -- '$DR_DEPLOY' '$DR_PINS_REMOTE' '$DR_STATE'" < "$HERE/remote-start-gateway.sh") \
  || fail "the AI server did not start: $result"
case "$result" in
  *GATEWAY_ALREADY_RUNNING*) say "    already running" ;;
  *GATEWAY_STARTED*) say "    started" ;;
  *) fail "unexpected answer from dr-train: $result" ;;
esac

say "3/4 Starting the web app and warming up the AI (this can take a few minutes)"
mkdir -p "$PRIVATE/demo-logs"
LOG="$PRIVATE/demo-logs/app-$(date +%Y%m%d-%H%M%S).log"
args=(-m scripts.qa.m1_server_app serve-regular --allow-remote-token-read
      --workspace-id "$DR_WORKSPACE" --prism-pins "$DR_PINS_LOCAL" --workstation "$DR_WORKSTATION"
      --app-port "$DR_APP_PORT" --model-port "$DR_MODEL_PORT")
case "$DR_IMAGES" in
  workspace) ;;
  public-samples) args+=(--public-samples) ;;
  public-folder) args+=(--public-samples --public-demo-folder "${DR_PUBLIC_FOLDER:?set DR_PUBLIC_FOLDER}") ;;
  *) fail "DR_IMAGES must be workspace, public-samples or public-folder" ;;
esac
(cd "$REPO" && exec "$PY" "${args[@]}") > "$LOG" 2>&1 &
APP_PID=$!
echo "$APP_PID" > "$PRIVATE/demo-logs/app.pid"
trap 'kill "$APP_PID" 2>/dev/null || true' EXIT INT TERM

waited=0
until grep -q '"phase": "SERVING"' "$LOG" 2>/dev/null; do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    code=$(grep -oE '[A-Z][A-Z0-9_]{6,}' "$LOG" | tail -1 || true)
    fail "the web app stopped while starting (${code:-see $LOG})"
  fi
  [ "$waited" -lt 420 ] || fail "the web app did not finish starting in 7 minutes (see $LOG)"
  printf '.'; sleep 5; waited=$((waited + 5))
done
say ""

say "4/4 Opening $APP_URL"
cmd.exe /c start "" "$APP_URL" >/dev/null 2>&1

say ""
say "Ready. Keep this window open while you use the app."
say "Close this window (or press Ctrl+C) to stop the web app."
say "The AI server on dr-train releases the GPU by itself after about 5 minutes without work."
wait "$APP_PID"
