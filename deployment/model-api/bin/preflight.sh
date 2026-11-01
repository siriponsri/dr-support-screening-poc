#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
: "${REMOTE_MODEL_TOKEN:?Inject a private demo token in the environment}"
: "${USPEC_MODEL_DIR:?Set exact verified USPEC artifact directory}"
: "${PRISM_SOURCE:?Set exact locked PRISM source directory}"
: "${PRISM_WEIGHTS:?Set exact PRISM weights directory}"
: "${RETFOUND_SOURCE:?Set exact verified RETFound source directory}"
: "${RETFOUND_WEIGHTS:?Set exact verified RETFound checkpoint path}"
for p in "$USPEC_MODEL_DIR/manifest.json" "$USPEC_MODEL_DIR/grading_state.pt" "$PRISM_SOURCE/.git" "$PRISM_WEIGHTS/manifest.json" "$RETFOUND_SOURCE/.git" "$RETFOUND_WEIGHTS"; do
  [[ -e "$p" ]] || { echo "Missing required verified asset: $p" >&2; exit 2; }
done
command -v docker >/dev/null
docker compose version >/dev/null
docker compose -f "$ROOT/deployment/model-api/compose.yml" config --quiet
echo 'PASS: Docker Compose and required private asset paths are present.'
