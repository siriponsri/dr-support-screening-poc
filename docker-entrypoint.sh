#!/bin/sh
# Container entrypoint for the multi-profile DR Support Screening POC image.
#
# Resolves APP_PROFILE/PORT at runtime, ensures the upstream model sources and
# weights are present when the model_api or full profile is selected, then
# execs uvicorn. The CPU-only review profile never tries to fetch weights.

set -eu

APP_PROFILE="${APP_PROFILE:-model_api}"
MODEL_RUNTIME="${MODEL_RUNTIME:-local}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7860}"
WORKERS="${WORKERS:-1}"

export APP_PROFILE MODEL_RUNTIME HOST PORT

echo "[entrypoint] APP_PROFILE=${APP_PROFILE} MODEL_RUNTIME=${MODEL_RUNTIME} HOST=${HOST} PORT=${PORT}"

case "${APP_PROFILE}" in
  review)
    # Review workstation: enforce remote inference, no weights required.
    if [ "${MODEL_RUNTIME}" != "remote" ]; then
      echo "[entrypoint] APP_PROFILE=review requires MODEL_RUNTIME=remote" >&2
      exit 1
    fi
    if [ -z "${REMOTE_MODEL_URL:-}" ]; then
      echo "[entrypoint] APP_PROFILE=review requires REMOTE_MODEL_URL" >&2
      exit 1
    fi
    # Default port for the review workstation is 8000 unless overridden.
    : "${PORT:=8000}"
    export PORT
    ;;
  model_api|full)
    # GPU deployment: pin weights + source revisions. The setup_models helper
    # is idempotent — already-verified files are skipped. Fail loudly if a
    # verification fails (this is a deploy-time concern, not silent skip).
    echo "[entrypoint] Acquiring / verifying pinned model sources and weights..."
    python -m dr_support.setup_models --model all
    ;;
  *)
    echo "[entrypoint] Unknown APP_PROFILE='${APP_PROFILE}'; expected review|model_api|full" >&2
    exit 1
    ;;
esac

echo "[entrypoint] Starting uvicorn workers=${WORKERS}..."
exec uvicorn dr_support.app:app_factory \
    --host "${HOST}" --port "${PORT}" --workers "${WORKERS}" \
    --log-level info
