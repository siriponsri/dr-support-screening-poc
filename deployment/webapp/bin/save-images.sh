#!/bin/sh
# On a machine with internet: build and save the images to one file for a hospital network without internet.
# Then copy the file and this package, and run load-images.sh there. Prints the file's SHA-256 for checking.
set -eu
. "$(dirname "$0")/common.sh"
set -a; . "$ENV_FILE"; set +a
compose build review
compose pull postgres https
out=${1:-dr-screening-webapp-${DR_SCREENING_IMAGE_TAG:-local}.tar}
docker save -o "$out" "dr-screening/review:${DR_SCREENING_IMAGE_TAG:-local}" postgres:16-alpine caddy:2.8-alpine
sha256sum "$out"
