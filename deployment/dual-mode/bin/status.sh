#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
PROJECT=${COMPOSE_PROJECT_NAME:-dr-screening-dual-mode}
PROFILE=${DUAL_MODE_GPU_PROFILE:?Set DUAL_MODE_GPU_PROFILE}
docker compose -p "$PROJECT" --profile "$PROFILE" -f "$ROOT/deployment/dual-mode/compose.yml" ps
