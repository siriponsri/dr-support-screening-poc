#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
"$(dirname "${BASH_SOURCE[0]}")/preflight.sh"
export DR_SCREENING_IMAGE_TAG=${DR_SCREENING_IMAGE_TAG:-candidate}
docker compose -f "$ROOT/deployment/model-api/compose.yml" build "$@"
