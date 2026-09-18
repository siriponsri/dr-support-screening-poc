#!/usr/bin/env bash
# =============================================================================
# Lightning AI Studio — one-time setup script (idempotent).
# =============================================================================
#
# Purpose
# -------
# Prepare a Lightning AI Studio GPU workspace so that
# `scripts/start_lightning.sh` can serve the existing FastAPI `model_api`
# surface. The script intentionally does NOT introduce a second
# dependency-resolution path: it reuses the v0.4.0 / v0.5.0 / v0.6.0 logic
# that already lives in `pyproject.toml` and `dr_support/setup_models.py`.
#
# Steps
# -----
#   1. Use / create a Python virtualenv under `.venv` (Lightning Studios
#      ship with Python 3.11; the project requires 3.11 / 3.12).
#   2. Upgrade pip / wheel / setuptools.
#   3. `pip install -e ".[models,test]"` — the editable install pulls the
#      CUDA-enabled torch stack from the default index. (For a CUDA 12.1
#      wheel, install torch+torchvision manually from
#      `download.pytorch.org/whl/cu121` first; see the README for details.)
#   4. Run `python -m dr_support.setup_models --model all` to acquire and
#      SHA256-verify the pinned RETFound + PRISM-DR sources and weights
#      under `local-state/bridge/`. The script is idempotent — already
#      downloaded and verified assets are not re-fetched.
#
# Persistence
# -----------
# Lightning Studios have a persistent home directory; the project's
# `local-state/bridge/` cache survives Studio restarts, so subsequent
# runs of this setup script are cheap no-ops and `setup_models` does not
# re-download the multi-GB weights.
#
# What this script does NOT do
# ----------------------------
#   - It does NOT commit checkpoints to git (the project's `.gitignore`
#     excludes `local-state/`, `*.pt`, `*.pth`, `*.zip`).
#   - It does NOT configure the bearer-token secret; that is an env var
#     the owner sets in the Studio's "Environment variables" panel before
#     running `start_lightning.sh`. The token never appears in this
#     script or any log output.
#   - It does NOT require a container engine; Lightning Studios already
#     provide a Linux runtime + GPU, no additional layer is needed.
# =============================================================================

set -euo pipefail

# Resolve repo root to the directory containing this script. Lightning
# Studios run Linux so `readlink -f` is safe.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." &>/dev/null && pwd)"

cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "[setup_lightning] ${PYTHON_BIN} is not on PATH; Lightning Studios usually provide python3.11 or python3.12." >&2
    exit 1
fi

# 1. Virtualenv. Skip when one already exists at .venv or when the
# operator points VENV_DIR somewhere else (e.g. a Studio-managed env).
VENV_DIR="${VENV_DIR:-${REPO_ROOT}/.venv}"
if [ ! -d "${VENV_DIR}" ]; then
    echo "[setup_lightning] Creating virtualenv at ${VENV_DIR}"
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck source=/dev/null
. "${VENV_DIR}/bin/activate"

# 2. Build tooling.
python -m pip install --upgrade pip wheel setuptools

# 3. Project + model deps. The CUDA-enabled torch stack is the operator's
# responsibility — Lightning Studios default to a CUDA 12.x runtime and
# the wheel index at https://download.pytorch.org/whl/cu121 matches the
# project. If the Studio's torch build is the CPU wheel the operator can
# install torch manually first; see the operator runbook.
python -m pip install -e ".[models,test]"

# 4. Acquire + verify model sources + weights under local-state/bridge/.
# `setup_models` is idempotent and SHA256-verifies every checkpoint
# against the pinned hashes in `dr_support/providers/{retfound,prism}.py`
# and `dr_support/providers/prism_assets.json`.
python -m dr_support.setup_models --model all

echo "[setup_lightning] Done."
echo "[setup_lightning] Persistent asset cache: ${REPO_ROOT}/local-state/bridge"
echo "[setup_lightning] Next: set REMOTE_MODEL_TOKEN in the Studio's environment variables, then run scripts/start_lightning.sh"
