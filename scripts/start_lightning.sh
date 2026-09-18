#!/usr/bin/env bash
# =============================================================================
# Lightning AI Studio — start script for the v0.6.0 model_api profile.
# =============================================================================
#
# Purpose
# -------
# Launch the existing `python -m dr_support.run` (FastAPI `model_api`) on a
# Lightning AI Studio GPU workspace. The script intentionally does NOT use
# Docker, NOT rewrite the FastAPI app into LitServe, and NOT introduce a new
# HTTP surface. The contract served on port 8000 is exactly:
#
#   GET  /health
#   GET  /v1/models
#   POST /v1/predict/dr
#   POST /v1/predict/lesions
#
# Hardware target
# ---------------
# Nvidia T4 small (matches the v0.4.0 HF Docker Space and v0.5.0 Modal targets).
# The script verifies CUDA is actually visible BEFORE starting uvicorn so the
# operator sees a loud failure in the Studio logs instead of the server
# silently degrading to CPU at the first inference call.
#
# Public port
# -----------
# Lightning AI Studio exposes the chosen port via the **Port** plugin
# (right-side panel) once the Studio is running. The Studio assigns a public
# URL that the local clinician workstation copies into `REMOTE_MODEL_URL` in
# its own `.env`. See `docs/LIGHTNING_DEPLOYMENT.md` for the full runbook.
#
# Stopping the GPU
# ----------------
# The operator stops the Studio (or sets it to sleep via the auto-sleep
# toggle) when acceptance is complete so Lightning credits are not consumed
# unnecessarily. This script does NOT enable auto-sleep itself; that is a
# Studio-level setting.
# =============================================================================

set -euo pipefail

# Production env for the model_api profile. Same contract as the HF Docker
# Space (`Dockerfile`) and the Modal adapter (`modal_app.py`).
export APP_PROFILE="${APP_PROFILE:-model_api}"
export MODEL_RUNTIME="${MODEL_RUNTIME:-local}"
export INFERENCE_DEVICE="${INFERENCE_DEVICE:-cuda:0}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export WORKERS="${WORKERS:-1}"

# Refuse to run unless the studio actually exposes a CUDA device. The
# `dr_support.runtime.assert_cuda_ready` check inside uvicorn would also
# catch this, but a pre-flight check surfaces the failure in the Studio
# logs before any uvicorn worker boots.
if ! command -v python >/dev/null 2>&1; then
    echo "[start_lightning] python is not on PATH; activate a venv or install Python first." >&2
    exit 1
fi

if ! python -c 'import torch; assert torch.cuda.is_available(), "no CUDA runtime visible"' >/dev/null 2>&1; then
    echo "[start_lightning] CUDA is NOT available on this Studio." >&2
    echo "[start_lightning] INFERENCE_DEVICE=${INFERENCE_DEVICE} was requested but no CUDA runtime is visible." >&2
    echo "[start_lightning] The model_api profile refuses to silently fall back to CPU." >&2
    echo "[start_lightning] Either:" >&2
    echo "  - select a GPU machine type in the Studio (T4 is the default), or" >&2
    echo "  - set INFERENCE_DEVICE=cpu for local CPU-only contract tests." >&2
    exit 2
fi

echo "[start_lightning] APP_PROFILE=${APP_PROFILE} MODEL_RUNTIME=${MODEL_RUNTIME} INFERENCE_DEVICE=${INFERENCE_DEVICE}"
echo "[start_lightning] Serving on ${HOST}:${PORT} with WORKERS=${WORKERS}"
echo "[start_lightning] Expose port ${PORT} via the Studio 'Port' plugin to obtain a public URL."

# Single-worker invariant: the api-level RLock keeps GPU activation memory
# bounded by one forward pass. WORKERS > 1 would each load the model into
# VRAM and exhaust a T4 within seconds.
if [ "${WORKERS}" != "1" ]; then
    echo "[start_lightning] WORKERS=${WORKERS} is not supported; this deployment is single-worker to avoid duplicate model loads." >&2
    exit 1
fi

exec python -m dr_support.run
