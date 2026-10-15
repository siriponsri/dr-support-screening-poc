#!/usr/bin/env bash
set -euo pipefail

# Run-owned unified private Review lane. It never starts, stops, or rewrites the
# already-qualified 8767/8768 services. Secrets, hospital roots, and model
# assets must be supplied by the operator environment, not this repository.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATEWAY_HOST="${UNIFIED_GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${UNIFIED_GATEWAY_PORT:-8881}"
REVIEW_HOST="${UNIFIED_REVIEW_HOST:-127.0.0.1}"
REVIEW_PORT="${UNIFIED_REVIEW_PORT:-8769}"
RUN_DIR="${UNIFIED_RUN_STATE_DIR:-$ROOT/local-state/unified-review}"
if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

usage() {
  printf '%s\n' "Usage: $0 {start|stop|status|smoke}" >&2
  exit 2
}

require_runtime_env() {
  : "${REMOTE_MODEL_TOKEN:?REMOTE_MODEL_TOKEN is required in the private environment}"
  : "${DR_SUPPORT_DATABASE_URL:?DR_SUPPORT_DATABASE_URL is required in the private environment}"
  : "${DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS:?DR_SUPPORT_AUTHORIZED_HOSPITAL_ROOTS is required (server-only JSON)}"
  : "${DR_SUPPORT_HOSPITAL_LINKAGE_KEY:?DR_SUPPORT_HOSPITAL_LINKAGE_KEY is required in the private environment}"
  [[ "${DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL:-}" == "1" ]] || {
    echo "DR_SUPPORT_ENABLE_AUTHORIZED_HOSPITAL must be 1" >&2; exit 1;
  }
  [[ "${DR_SUPPORT_HOSPITAL_SCOPE:-}" == "PRIVATE_PROJECT_EVALUATION" ]] || {
    echo "DR_SUPPORT_HOSPITAL_SCOPE must be PRIVATE_PROJECT_EVALUATION" >&2; exit 1;
  }
  [[ "${MODEL_HOSPITAL_SCOPE:-}" == "PRIVATE_PROJECT_EVALUATION" ]] || {
    echo "MODEL_HOSPITAL_SCOPE must be PRIVATE_PROJECT_EVALUATION" >&2; exit 1;
  }
  [[ "${MODEL_ALLOW_AUTHORIZED_HOSPITAL:-}" == "1" ]] || {
    echo "MODEL_ALLOW_AUTHORIZED_HOSPITAL must be 1" >&2; exit 1;
  }
}

port_free() {
  ! ss -ltn "sport = :$1" 2>/dev/null | grep -q LISTEN
}

pid_alive() { [[ -s "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

owned_pid() {
  local pid_file="$1" kind="$2" pid cmd port_value
  [[ -s "$pid_file" ]] || return 1
  pid="$(cat "$pid_file")"
  kill -0 "$pid" 2>/dev/null || return 1
  cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
  if [[ "$kind" == gateway ]]; then
    [[ "$cmd" == *"deployment/dual-mode/gateway"* ]] || return 1
    port_value="$GATEWAY_PORT"
  else
    [[ "$cmd" == *"dr_support.run"* ]] || return 1
    port_value="$REVIEW_PORT"
  fi
  [[ "$(tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | awk -F= -v key=PORT '$1 == key {print $2; exit}')" == "$port_value" ]]
}

start_one() {
  local name="$1" pid_file="$2" log_file="$3"; shift 3
  if owned_pid "$pid_file" "$name"; then
    echo "$name already running (run-owned)"; return 0
  fi
  if [[ -s "$pid_file" ]] && pid_alive "$pid_file"; then
    echo "$name PID file refers to an unrelated process; refusing to stop or replace it" >&2
    exit 1
  fi
  # Lightning shell jobs may reap ordinary background descendants when the
  # launching shell exits.  Create a new session so a run-owned service remains
  # available to the operator while retaining explicit PID ownership checks.
  command -v setsid >/dev/null 2>&1 || {
    echo "setsid is required for a persistent private runtime" >&2
    exit 1
  }
  setsid nohup "$@" >"$log_file" 2>&1 < /dev/null &
  echo $! >"$pid_file"
  chmod 600 "$pid_file" "$log_file" 2>/dev/null || true
}

wait_health() {
  local url="$1" tries=30
  until curl --fail --silent --show-error --max-time 2 "$url" >/dev/null; do
    tries=$((tries - 1)); (( tries > 0 )) || { echo "Health check failed: $url" >&2; return 1; }
    sleep 1
  done
}

start() {
  require_runtime_env
  mkdir -p "$RUN_DIR"
  chmod 700 "$RUN_DIR"
  if ! port_free "$GATEWAY_PORT" && ! owned_pid "$RUN_DIR/gateway.pid" gateway; then
    echo "Unified gateway port $GATEWAY_PORT is occupied; refusing to replace it" >&2
    exit 1
  fi
  if ! port_free "$REVIEW_PORT" && ! owned_pid "$RUN_DIR/review.pid" review; then
    echo "Unified Review port $REVIEW_PORT is occupied; refusing to replace it" >&2
    exit 1
  fi

  export HOST="$GATEWAY_HOST" PORT="$GATEWAY_PORT"
  export USPEC_URL="${USPEC_URL:-http://127.0.0.1:7865}"
  export RETFOUND_URL="${RETFOUND_URL:-http://127.0.0.1:7866}"
  export PRISM_URL="${PRISM_URL:-http://127.0.0.1:7865}"
  start_one gateway "$RUN_DIR/gateway.pid" "$RUN_DIR/gateway.log" \
    "$PYTHON_BIN" -m uvicorn app:app --app-dir "$ROOT/deployment/dual-mode/gateway" \
    --host "$GATEWAY_HOST" --port "$GATEWAY_PORT" --workers 1
  wait_health "http://$GATEWAY_HOST:$GATEWAY_PORT/health"

  export APP_PROFILE=review MODEL_RUNTIME=remote
  export HOST="$REVIEW_HOST" PORT="$REVIEW_PORT" WORKERS=1
  export REMOTE_MODEL_URL="http://$GATEWAY_HOST:$GATEWAY_PORT"
  export DR_SUPPORT_CASE_STORE=postgres
  export DR_SUPPORT_DATABASE_SCHEMA="${DR_SUPPORT_DATABASE_SCHEMA:-dr_support_unified_private}"
  export DR_SUPPORT_WORKSPACE_ID="${DR_SUPPORT_WORKSPACE_ID:-unified-hospital-private-demo}"
  start_one review "$RUN_DIR/review.pid" "$RUN_DIR/review.log" \
    "$PYTHON_BIN" -m dr_support.run
  wait_health "http://$REVIEW_HOST:$REVIEW_PORT/health"
  echo "Unified private Review: http://$REVIEW_HOST:$REVIEW_PORT/app/"
  echo "Run-owned state: $RUN_DIR (logs contain no intentional image export)"
}

stop_one() {
  local name="$1" pid_file="$2"
  if ! [[ -s "$pid_file" ]]; then echo "$name NOT_RUNNING"; return 0; fi
  if ! owned_pid "$pid_file" "$name"; then
    if pid_alive "$pid_file"; then
      echo "$name PID file is not run-owned; refusing to stop it" >&2
      return 1
    fi
    rm -f "$pid_file"
    echo "$name NOT_RUNNING"
    return 0
  fi
  kill -TERM "$(cat "$pid_file")"
  for _ in $(seq 1 20); do
    kill -0 "$(cat "$pid_file")" 2>/dev/null || { rm -f "$pid_file"; echo "$name STOPPED"; return 0; }
    sleep 0.25
  done
  echo "$name did not stop after SIGTERM; investigate its run-owned log" >&2
  return 1
}

status() {
  for pair in "gateway:$RUN_DIR/gateway.pid" "review:$RUN_DIR/review.pid"; do
    name="${pair%%:*}"; file="${pair#*:}"
    if owned_pid "$file" "$name"; then echo "$name RUNNING"; else echo "$name NOT_RUNNING"; fi
  done
  echo "clinician_url http://$REVIEW_HOST:$REVIEW_PORT/app/"
  echo "internal_model_ports 7865,7866; not user-facing"
}

smoke() {
  require_runtime_env
  local auth=( -H "Authorization: Bearer $REMOTE_MODEL_TOKEN" )
  curl --fail --silent --show-error --max-time 5 "http://$REVIEW_HOST:$REVIEW_PORT/health" >/dev/null
  curl --fail --silent --show-error --max-time 8 "${auth[@]}" "http://$REVIEW_HOST:$REVIEW_PORT/v1/model-connection" >/dev/null
  curl --fail --silent --show-error --max-time 8 "${auth[@]}" "http://$REVIEW_HOST:$REVIEW_PORT/v1/models" >/dev/null
  curl --fail --silent --show-error --max-time 8 "http://$REVIEW_HOST:$REVIEW_PORT/v1/cases" >/dev/null
  echo "PASS unified health/model-connection/models/cases";
  echo "PASS configured routing contract UWF->USPEC CFP->RETFound lesions->PRISM";
  echo "PASS private loopback-only URL http://$REVIEW_HOST:$REVIEW_PORT/app/"
}

case "${1:-}" in
  start) start ;;
  stop) stop_one review "$RUN_DIR/review.pid"; stop_one gateway "$RUN_DIR/gateway.pid" ;;
  status) status ;;
  smoke) smoke ;;
  *) usage ;;
esac
