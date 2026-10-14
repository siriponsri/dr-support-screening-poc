#!/usr/bin/env bash
set -euo pipefail
service=${1:?Usage: stop.sh retfound|uspec|prism|all}
project=dr-screening-m1
case "$service" in
  retfound|uspec|prism)
    services=("$service")
    ;;
  all)
    services=(retfound uspec prism)
    ;;
  *)
    echo 'Unknown service' >&2
    exit 2
    ;;
esac

# Stopping a container must not require asset paths or runtime credentials.
# Scope every action to this compose project and explicit service labels.
for name in "${services[@]}"; do
  mapfile -t ids < <(docker ps -q \
    --filter "label=com.docker.compose.project=$project" \
    --filter "label=com.docker.compose.service=$name")
  if ((${#ids[@]})); then
    docker stop "${ids[@]}"
  else
    printf 'Already stopped: %s\n' "$name"
  fi
done
