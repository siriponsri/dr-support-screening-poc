#!/bin/sh
# Shared settings for the web app package scripts. Sourced, not run.
PKG_DIR=$(cd "$(dirname "$0")/.." && pwd)
# Git Bash on Windows would rewrite container paths such as /data/config; harmless on Linux.
export MSYS_NO_PATHCONV=1
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/webapp.env}
if command -v cygpath >/dev/null 2>&1; then PKG_DIR=$(cygpath -m "$PKG_DIR"); ENV_FILE=$(cygpath -m "$ENV_FILE"); fi
[ -f "$ENV_FILE" ] || { echo "Settings file not found: $ENV_FILE (copy webapp.env.example there)"; exit 1; }
if grep -v '^[[:space:]]*#' "$ENV_FILE" | grep -q 'REPLACE'; then echo "Settings file still has REPLACE values: $ENV_FILE"; exit 1; fi
compose() { docker compose --env-file "$ENV_FILE" -f "$PKG_DIR/compose.yml" "$@"; }
