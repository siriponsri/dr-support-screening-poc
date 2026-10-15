#!/usr/bin/env bash
set -euo pipefail
service=${1:?Usage: smoke.sh retfound|uspec|prism [base-url]}
case "$service" in
 retfound) url=${2:-http://127.0.0.1:${RETFOUND_PORT:-7864}} ;;
 uspec) url=${2:-http://127.0.0.1:${USPEC_PORT:-7861}} ;;
 prism) url=${2:-http://127.0.0.1:${PRISM_PORT:-7862}} ;;
 *) echo 'Unknown service' >&2; exit 2 ;;
esac
python - "$url" <<'PY'
import json, sys, urllib.request
base=sys.argv[1].rstrip('/')
for path in ('/health','/v1/models'):
 with urllib.request.urlopen(base+path, timeout=5) as response:
  body=json.load(response)
  if path == '/health' and body.get('status') != 'PASS':
   raise SystemExit(f'FAIL: health status {body.get("status")}')
  if path == '/v1/models' and not body:
   raise SystemExit('FAIL: empty model descriptor list')
  print(path, 'PASS')
PY
