#!/bin/sh
# Load saved images on a machine without internet. Check the SHA-256 against the one printed by save-images.sh.
# Usage: load-images.sh <file.tar> <expected sha256>
set -eu
file=${1:?usage: load-images.sh <file.tar> <expected sha256>}
expected=${2:?usage: load-images.sh <file.tar> <expected sha256>}
actual=$(sha256sum "$file" | cut -d' ' -f1)
[ "$actual" = "$expected" ] || { echo "Checksum does not match; not loading."; exit 1; }
docker load -i "$file"
echo "Images loaded. Next: bin/start.sh"
