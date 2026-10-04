#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
if [[ -e grading_state.pt || -e local-state/bridge/grading_state.pt || -e .env ]]; then
  echo "BLOCKED: model artifact, runtime state, or private environment file is present." >&2
  exit 1
fi
if [[ ! -f scripts/release/model_artifacts.json ]]; then
  echo "BLOCKED: model identity manifest is missing." >&2
  exit 1
fi
echo "PASS: Model API release remains model-disabled and identity-only."
