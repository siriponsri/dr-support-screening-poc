#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
echo "NOT_RUN: no Model API process is started by this model-disabled release package."
exit 2
