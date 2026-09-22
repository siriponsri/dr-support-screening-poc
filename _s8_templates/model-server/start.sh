#!/usr/bin/env bash
# S8 TEMPLATE — normal startup must NOT download weights.
set -euo pipefail
export APP_PROFILE="${APP_PROFILE:-model_api}"
export MODEL_RUNTIME="${MODEL_RUNTIME:-local}"
export INFERENCE_DEVICE="${INFERENCE_DEVICE:-cuda:0}"
export WORKERS="${WORKERS:-1}"
# TODO: verify local model assets before launch and fail clearly if missing/mismatched.
exec python -m dr_support.run
