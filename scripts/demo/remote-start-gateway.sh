#!/bin/sh
# Runs ON dr-train (sent over the existing SSH route by start-dr-train-demo.sh).
# Starts the regular gateway from an existing deployment if nothing listens on 7860.
# CPU only: the GPU child starts later, on demand, inside AI hours. Never prints the token.
# Arguments: <deployment name> <PRISM pins path under the project> <state folder name>
set -eu
P=/home/siripon/projects/dr-model-api-qa
DEPLOY_NAME=$1
PINS_REL=$2
STATE_NAME=$3
case "$DEPLOY_NAME" in regular-[0-9]*-r[0-9]*) ;; *) echo "DEPLOYMENT_NAME_REJECTED"; exit 2 ;; esac
case "$PINS_REL" in regular/r[0-9]*-inputs/PRISM_WORKSPACE_PINS.json) ;; *) echo "PINS_PATH_REJECTED"; exit 2 ;; esac
case "$STATE_NAME" in r[0-9]*) ;; *) echo "STATE_NAME_REJECTED"; exit 2 ;; esac
D=$P/deployments/$DEPLOY_NAME
for required in "$D/scripts/model-server/regular_service.py" "$P/$PINS_REL" "$P/regular/$STATE_NAME" \
                "$P/regular/$STATE_NAME-lineage.json" "$P/m1-continuation-service-20261025/EXPECTED_BATCH_MODELS.json"; do
  test -e "$required" || { echo "MISSING $(basename "$required")"; exit 3; }
done
if ss -ltn | grep -q ':7860 '; then
  echo "GATEWAY_ALREADY_RUNNING"
  exit 0
fi
LOG=$P/regular/oneclick-$(date -u +%Y%m%dT%H%M%SZ).log
setsid nohup "$P/environments/prism-qa-torch213/bin/python" -I -B "$D/scripts/model-server/regular_service.py" serve \
  --deploy "$D" --models "$P/m1-continuation-service-20261025/EXPECTED_BATCH_MODELS.json" \
  --prism-pins "$P/$PINS_REL" --state "$P/regular/$STATE_NAME" --lineage "$P/regular/$STATE_NAME-lineage.json" \
  > "$LOG" 2>&1 < /dev/null &
echo $! > "$P/regular/oneclick-service.pid"
i=0
while [ $i -lt 60 ]; do
  if ss -ltn | grep -q ':7860 '; then echo "GATEWAY_STARTED"; exit 0; fi
  i=$((i + 1)); sleep 1
done
echo "GATEWAY_DID_NOT_START (see $(basename "$LOG"))"
exit 4
