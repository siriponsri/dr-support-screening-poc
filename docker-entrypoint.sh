#!/bin/sh
# Container entrypoint for the multi-profile DR Support Screening POC image.
#
# Asset strategy: download + verify at image build time
# -------------------------------------------------------
# The Dockerfile runs `python -m dr_support.setup_models --model all` once
# during `docker build`; weights and sources live under
# `/app/local-state/bridge` and are SHA256-verified at that point. This
# entrypoint does NOT re-download them — a cold start must be dominated by
# uvicorn + model lazy-loading, not multi-GB network IO.
#
# Responsibilities
# ----------------
# 1. Validate APP_PROFILE and required environment variables.
# 2. Refuse to start the review profile without REMOTE_MODEL_URL.
# 3. Refuse to start the model_api / full profile without the build-time
#    weights directory present (defence-in-depth; the resolver will surface
#    a clearer error inside Python if a single file is missing).
# 4. Reject WORKERS > 1 — duplicate uvicorn workers would each load the
#    model weights into VRAM and exhaust the T4 in seconds.
# 5. Exec the Python entrypoint `dr_support.run.main`.

set -eu

APP_PROFILE="${APP_PROFILE:-model_api}"
MODEL_RUNTIME="${MODEL_RUNTIME:-local}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-7860}"
WORKERS="${WORKERS:-1}"

export APP_PROFILE MODEL_RUNTIME HOST PORT WORKERS

echo "[entrypoint] APP_PROFILE=${APP_PROFILE} MODEL_RUNTIME=${MODEL_RUNTIME} HOST=${HOST} PORT=${PORT} WORKERS=${WORKERS}"

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
    # The review workstation defaults to 8000 unless the operator overrides
    # PORT explicitly. model_api uses 7860 for HF parity.
    if [ "${PORT}" = "7860" ] && [ -z "${PORT_OVERRIDE:-}" ]; then
      : "${PORT:=8000}"
      export PORT
    fi
    ;;
  model_api|full)
    # GPU deployment: the Dockerfile already ran `setup_models --model all`
    # during build, so the source / weight files MUST be present in the image.
    # We refuse to start if the cache directory is empty so a misconfigured
    # build cannot silently boot into a CPU-only fallback.
    if [ ! -d /app/local-state/bridge/sources/RETFound ] || \
       [ ! -d /app/local-state/bridge/sources/PRISM-DR ] || \
       [ ! -f /app/local-state/bridge/retfound-aptos.pth ] || \
       [ ! -d /app/local-state/bridge/prism ]; then
      echo "[entrypoint] model_api/full profile requires pre-built model assets under /app/local-state/bridge" >&2
      echo "[entrypoint] Re-run 'docker build' (which invokes 'python -m dr_support.setup_models --model all')" >&2
      exit 1
    fi
    ;;
  *)
    echo "[entrypoint] Unknown APP_PROFILE='${APP_PROFILE}'; expected review|model_api|full" >&2
    exit 1
    ;;
esac

# Single uvicorn worker: the GPU holds a process-wide lock on the model and
# sharing one worker avoids duplicate VRAM allocations.
if [ "${WORKERS}" != "1" ]; then
  echo "[entrypoint] WORKERS=${WORKERS} is not supported; this deployment is single-worker to avoid duplicate model loads" >&2
  exit 1
fi

echo "[entrypoint] Starting uvicorn..."
exec python -m dr_support.run
