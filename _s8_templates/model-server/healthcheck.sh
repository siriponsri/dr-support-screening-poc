#!/usr/bin/env bash
# S8 TEMPLATE — rewrite URL/token policy against final deployment.
set -euo pipefail
BASE_URL="${MODEL_API_BASE_URL:-http://127.0.0.1:8000}"
curl --fail --silent --show-error "$BASE_URL/health"
echo
curl --fail --silent --show-error "$BASE_URL/v1/models"
echo
