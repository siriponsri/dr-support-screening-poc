#!/bin/sh
# Runs ON dr-train. Gracefully stops the regular gateway that listens on 7860 (it stops its GPU child itself).
# Only a process whose command line is regular_service.py is signalled.
set -eu
pid=$(ss -ltnp 2>/dev/null | sed -n 's/.*127\.0\.0\.1:7860 .*pid=\([0-9]*\).*/\1/p' | head -1)
if [ -z "$pid" ]; then echo "GATEWAY_NOT_RUNNING"; exit 0; fi
case "$(tr '\0' ' ' < /proc/$pid/cmdline)" in
  *regular_service.py*serve*) ;;
  *) echo "PORT_7860_NOT_THE_GATEWAY"; exit 2 ;;
esac
kill -TERM "$pid"
i=0
while [ $i -lt 60 ]; do
  kill -0 "$pid" 2>/dev/null || { echo "GATEWAY_STOPPED"; exit 0; }
  i=$((i + 1)); sleep 1
done
echo "GATEWAY_STILL_STOPPING"
exit 3
