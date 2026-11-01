#!/usr/bin/env bash
set -euo pipefail

base_url="${MODEL_API_URL:-http://127.0.0.1:${PORT:-7860}}"
health="$(curl --silent --show-error --fail --max-time 10 "$base_url/health")"
models="$(curl --silent --show-error --fail --max-time 10 "$base_url/v1/models")"

printf '%s\n' "$health"
printf '%s\n' "$models"

if ! printf '%s' "$health" | grep -q '"status":"PASS"'; then
  echo "ERROR: Model API health did not report PASS." >&2
  exit 1
fi
echo "READY: /health and /v1/models responded successfully."
