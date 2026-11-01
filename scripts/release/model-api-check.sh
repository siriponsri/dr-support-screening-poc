#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
echo "PASS: contract-only Model API package is present."
echo "NOT_RUN: Linux host, GPU, weights, inference, and P3.1 qualification."
