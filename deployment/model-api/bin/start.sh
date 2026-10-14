#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
service=${1:?Usage: start.sh retfound|uspec|prism}
case "$service" in retfound|uspec|prism) ;; *) echo 'Unknown service' >&2; exit 2;; esac
"$(dirname "${BASH_SOURCE[0]}")/preflight.sh"
docker compose -p dr-screening-m1 -f "$ROOT/deployment/model-api/compose.yml" up -d --no-deps "$service"
