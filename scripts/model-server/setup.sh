#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

python_bin="${PYTHON_BIN:-python3}"
if ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "ERROR: $python_bin is required." >&2
  exit 1
fi

"$python_bin" - <<'PY'
import sys
if sys.version_info[:2] not in {(3, 11), (3, 12)}:
    raise SystemExit(f'Python 3.11 or 3.12 is required; found {sys.version.split()[0]}')
PY

if [[ ! -x .venv/bin/python ]]; then
  "$python_bin" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[models,dicom]'

export APP_PROFILE=model_api
export MODEL_RUNTIME=local
export INFERENCE_DEVICE="${INFERENCE_DEVICE:-cuda:0}"
export WORKERS="${WORKERS:-1}"
export DR_SUPPORT_RELAX_DEVICE="${DR_SUPPORT_RELAX_DEVICE:-0}"

echo "Acquiring pinned RETFound and PRISM-DR assets..."
.venv/bin/python -m dr_support.setup_models --model all --smoke
echo "READY: verified assets and completed synthetic smoke inference."
