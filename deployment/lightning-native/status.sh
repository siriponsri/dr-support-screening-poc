#!/usr/bin/env bash
set -euo pipefail
# Read-only status for the already-qualified native run. It never kills or
# replaces a process and does not print private paths, filenames, or tokens.
for port in 54329 7865 7866 8767 8768; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    printf 'PORT %s LISTENING\n' "$port"
  else
    printf 'PORT %s NOT_LISTENING\n' "$port"
  fi
done
