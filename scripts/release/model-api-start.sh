#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
echo "BLOCKED: model runtime is disabled in this release package. P3.1 host qualification is required before startup." >&2
exit 2
