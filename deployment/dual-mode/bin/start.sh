#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
"$ROOT/deployment/dual-mode/bin/preflight.sh"
PROJECT=${COMPOSE_PROJECT_NAME:-dr-screening-dual-mode}
docker compose -p "$PROJECT" --profile "$DUAL_MODE_GPU_PROFILE" -f "$ROOT/deployment/dual-mode/compose.yml" up -d
