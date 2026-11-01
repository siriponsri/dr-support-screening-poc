#!/usr/bin/env bash
set -euo pipefail
BASE=${GATEWAY_BASE_URL:-http://127.0.0.1:${GATEWAY_PORT:-8880}}
TOKEN=${REMOTE_MODEL_TOKEN:?Set the private gateway token}
python - "$BASE" "$TOKEN" <<'PY'
import json, sys, urllib.request, urllib.error
base, token = sys.argv[1].rstrip('/'), sys.argv[2]
def get(path, auth=True):
    request = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token} if auth else {})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()
status, body = get('/health', auth=False)
assert status == 200 and body.get('status') == 'PASS', (status, body)
expected_models = {'uspec-uwf-grading', 'retfound-aptos5', 'prism-dr-5fold'}
for path in ('/v1/models', '/v1/capabilities'):
    status, body = get(path)
    assert status == 200 and isinstance(body, list) and body, (path, status, body)
    if path == '/v1/models':
        advertised = {item.get('model_id') for item in body if isinstance(item, dict)}
        assert expected_models <= advertised, (path, advertised)
status, _ = get('/v1/models', auth=False)
assert status == 401, status
print('PASS: gateway health, authenticated metadata, and unauthenticated rejection')
PY
