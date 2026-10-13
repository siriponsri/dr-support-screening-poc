#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

python_bin="${MODEL_API_PYTHON:-$repo_root/.venv/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "ERROR: Model API Python is missing. Set MODEL_API_PYTHON or run scripts/model-server/setup.sh." >&2
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
export MODEL_API_PROVIDER_SET="${MODEL_API_PROVIDER_SET:-legacy}"

# Read-only verification. This command never downloads or clones anything.
"$python_bin" -m dr_support.setup_models --model "$MODEL_API_PROVIDER_SET" --verify
exec "$python_bin" -m dr_support.run
