#!/bin/sh
# Stop the web app. Data (database volume and folders) is kept.
set -eu
. "$(dirname "$0")/common.sh"
compose stop
echo "Stopped. Data is kept."
