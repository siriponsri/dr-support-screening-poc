#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
PROFILE=${DUAL_MODE_GPU_PROFILE:?Set DUAL_MODE_GPU_PROFILE to lightning-t4, ceo-p40, or hospital-3090}
case "$PROFILE" in lightning-t4|ceo-p40|hospital-3090) ;; *) echo "Unsupported profile: $PROFILE" >&2; exit 2 ;; esac
: "${MODEL_API_BASE_IMAGE:?Set a profile-specific MODEL_API_BASE_IMAGE}"
[[ "$MODEL_API_BASE_IMAGE" != REPLACE_* ]] || { echo 'Refusing placeholder base image' >&2; exit 2; }
: "${REMOTE_MODEL_TOKEN:?Inject a private model token}"; [[ "$REMOTE_MODEL_TOKEN" != REPLACE_* ]] || { echo 'Refusing placeholder token' >&2; exit 2; }
: "${DR_SUPPORT_POSTGRES_PASSWORD:?Inject a private PostgreSQL password}"; [[ "$DR_SUPPORT_POSTGRES_PASSWORD" != REPLACE_* ]] || { echo 'Refusing placeholder database password' >&2; exit 2; }
: "${USPEC_MODEL_DIR:?Set exact verified USPEC artifact directory}"
: "${PRISM_SOURCE:?Set exact locked PRISM source directory}"
: "${PRISM_WEIGHTS:?Set exact PRISM weights directory}"
: "${RETFOUND_SOURCE:?Set exact verified RETFound source directory}"
: "${RETFOUND_WEIGHTS:?Set exact verified RETFound checkpoint path}"
for p in "$USPEC_MODEL_DIR/manifest.json" "$USPEC_MODEL_DIR/grading_state.pt" "$PRISM_SOURCE/.git" "$PRISM_WEIGHTS/manifest.json" "$RETFOUND_SOURCE/.git" "$RETFOUND_WEIGHTS"; do
  [[ -e "$p" ]] || { echo "Missing required verified asset: $p" >&2; exit 2; }
done
command -v nvidia-smi >/dev/null || { echo 'nvidia-smi unavailable; CPU fallback is not permitted' >&2; exit 2; }
GPU_LINE=$(nvidia-smi --query-gpu=name,compute_cap,memory.total,driver_version --format=csv,noheader,nounits | head -n1)
[[ -n "$GPU_LINE" ]] || { echo 'No NVIDIA GPU detected' >&2; exit 2; }
GPU_NAME=$(printf "%s" "$GPU_LINE" | awk -F, '{gsub(/^ +| +$/, "", $1); print $1}'); COMPUTE_CAP=$(printf '%s' "$GPU_LINE" | awk -F, '{gsub(/^ +| +$/, "", $2); print $2}')
case "$PROFILE:$GPU_NAME:$COMPUTE_CAP" in
  lightning-t4:*Tesla\ T4*:7.5) ;;
  ceo-p40:*Tesla\ P40*:6.1) ;;
  hospital-3090:*RTX\ 3090*:8.6) ;;
  *) echo "GPU/profile mismatch: profile=$PROFILE actual=$GPU_LINE" >&2; exit 3 ;;
esac
docker compose version >/dev/null
: "${DR_SCREENING_SOURCE_COMMIT:?Set the exact 40-character source commit for the review build identity}"
[[ "$DR_SCREENING_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'DR_SCREENING_SOURCE_COMMIT must be a 40-character lowercase Git SHA' >&2; exit 2; }
export DR_SCREENING_IMAGE_TAG=${DR_SCREENING_IMAGE_TAG:-portable}
docker compose --profile "$PROFILE" -f "$ROOT/deployment/dual-mode/compose.yml" config --quiet
echo "PASS profile=$PROFILE gpu=$GPU_LINE"
