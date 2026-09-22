#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ ! -x .venv/bin/python ]]; then
  echo "ERROR: .venv is missing. Run scripts/model-server/setup.sh once while online." >&2
  exit 1
fi

export APP_PROFILE=model_api
export MODEL_RUNTIME=local
export INFERENCE_DEVICE="${INFERENCE_DEVICE:-cuda:0}"
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-7860}"
export WORKERS="${WORKERS:-1}"
export MODEL_REQUIRE_VERIFIED_ASSETS=1
export DR_SUPPORT_RELAX_DEVICE="${DR_SUPPORT_RELAX_DEVICE:-0}"

# Read-only verification. This command never downloads or clones anything.
.venv/bin/python -m dr_support.setup_models --model all --verify
exec .venv/bin/python -m dr_support.run
