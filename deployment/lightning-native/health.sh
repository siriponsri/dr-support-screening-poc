#!/usr/bin/env bash
set -euo pipefail
auth_args=()
if [[ -n "${REMOTE_MODEL_TOKEN:-}" ]]; then
  auth_args=(-H "Authorization: Bearer ${REMOTE_MODEL_TOKEN}")
fi
for url in \
  http://127.0.0.1:7865/health \
  http://127.0.0.1:7866/health \
  http://127.0.0.1:8767/health \
  http://127.0.0.1:8768/health; do
  curl --fail --silent --show-error --max-time 5 "${auth_args[@]}" "$url" >/dev/null
  printf 'PASS %s\n' "$url"
done
for url in \
  http://127.0.0.1:7865/v1/models \
  http://127.0.0.1:7866/v1/models \
  http://127.0.0.1:8767/v1/dataset/manifest \
  http://127.0.0.1:8768/v1/dataset/manifest; do
  curl --fail --silent --show-error --max-time 5 "${auth_args[@]}" "$url" >/dev/null
  printf 'PASS %s\n' "$url"
done
