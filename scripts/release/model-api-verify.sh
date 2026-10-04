#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ ! -f scripts/release/model_artifacts.json ]]; then
  echo "BLOCKED: model identity manifest is missing." >&2
  exit 1
fi
if find . -path './.git' -prune -o -path './local-state' -prune -o \
  \( -name '*.pt' -o -name '*.pth' -o -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print -quit | grep -q .; then
  echo "BLOCKED: a model weight or runtime database is present; no qualification is performed." >&2
  exit 1
fi
echo "PASS: software contracts and expected artifact identity are present."
echo "NOT_RUN: weights, GPU runtime, inference, and P3.1 host qualification."
