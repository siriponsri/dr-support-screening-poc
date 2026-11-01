#!/usr/bin/env bash
# Make the offline install bundle for a hospital server without internet.
# Run on a machine WITH internet and Docker (Linux x86_64, or Docker Desktop with Git Bash). No GPU needed.
#
#   deployment/hospital-server/bin/make-offline-bundle.sh [output-folder]
#
# Produces <output-folder>/dr-screening-hospital-<tag>.tar and its .sha256 file. Inside:
#   dr-screening/   the project source at the current commit (git archive: tracked files only)
#   images/         every Docker image the hospital profile needs, saved and compressed
#   BUNDLE_INFO     version and image list      SHA256SUMS  checksum of every file
#   README.txt      what to do on the server
# AI model weights are NOT included (they are not in Git); README.txt says where to put them.
set -euo pipefail
export MSYS_NO_PATHCONV=1

PKG=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$PKG/../.." && pwd)
PROFILE=hospital-3090
PLATFORM=linux/amd64

say() { printf '%s\n' "$*"; }
fail() { printf '\nStopped: %s\n' "$*" >&2; exit 1; }
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

for tool in docker git gzip sha256sum tar; do
  command -v "$tool" >/dev/null 2>&1 || fail "$tool is required on this machine."
done
docker info >/dev/null 2>&1 || fail "Docker is not running."
docker compose version >/dev/null 2>&1 || fail "the Docker Compose plugin is required."

COMMIT=$(git -C "$REPO" rev-parse HEAD)
[[ "$COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "could not read the current commit."
if [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then
  say "Note: uncommitted changes are not included; the bundle is made from commit ${COMMIT:0:12}."
fi
TAG=git-${COMMIT:0:12}
NAME=dr-screening-hospital-$TAG
OUT=${1:-$PWD}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
WORK=$OUT/$NAME
[ ! -e "$WORK" ] && [ ! -e "$OUT/$NAME.tar" ] || fail "$WORK or $OUT/$NAME.tar already exists; remove it or choose another folder."
BASE_IMAGE=$(sed -n 's/^MODEL_API_BASE_IMAGE=//p' "$PKG/hospital.env.example" | head -n1)
[ -n "$BASE_IMAGE" ] || fail "MODEL_API_BASE_IMAGE is missing from hospital.env.example."
IMAGES=("dr-screening/review:$TAG" "dr-screening/model-gateway:$TAG" "dr-screening/uspec-api:$TAG"
        "dr-screening/prism-api:$TAG" "dr-screening/retfound-api:$TAG" postgres:16-alpine caddy:2.8-alpine)

say "Making $NAME"
say "1/5 Exporting the source of commit ${COMMIT:0:12}"
mkdir -p "$WORK/images"
git -C "$REPO" archive --format=tar --prefix=dr-screening/ "$COMMIT" | tar -x -C "$WORK"
SRC=$WORK/dr-screening

# Build-only settings: compose needs every variable filled in to read the files. None of these values is a
# secret or is shipped; the hospital installer writes the real private settings on the server.
BUILD_TMP=$(mktemp -d)
trap 'rm -rf "$BUILD_TMP"' EXIT
mkdir -p "$BUILD_TMP/empty"
EMPTY=$(native "$BUILD_TMP/empty")
cat > "$BUILD_TMP/build.env" <<EOF
DUAL_MODE_GPU_PROFILE=$PROFILE
DR_SCREENING_SOURCE_COMMIT=$COMMIT
DR_SCREENING_IMAGE_TAG=$TAG
MODEL_API_BASE_IMAGE=$BASE_IMAGE
DR_SUPPORT_POSTGRES_DB=build_only
DR_SUPPORT_POSTGRES_USER=build_only
DR_SUPPORT_POSTGRES_PASSWORD=build-only-not-a-secret
REMOTE_MODEL_TOKEN=build-only-not-a-secret
USPEC_MODEL_DIR=$EMPTY
PRISM_SOURCE=$EMPTY
PRISM_WEIGHTS=$EMPTY
RETFOUND_SOURCE=$EMPTY
RETFOUND_WEIGHTS=$EMPTY
DR_DATA_DIR=$EMPTY
DR_IMAGES_DIR=$EMPTY
DR_SITE_ADDRESS=localhost
EOF
compose() {
  docker compose -f "$(native "$SRC/deployment/dual-mode/compose.yml")" \
    -f "$(native "$SRC/deployment/hospital-server/compose.override.yml")" --profile "$PROFILE" \
    --env-file "$(native "$BUILD_TMP/build.env")" "$@"
}

say "2/5 Building the five DR Screening images for $PLATFORM (20 to 40 minutes the first time)"
DOCKER_DEFAULT_PLATFORM=$PLATFORM compose build review gateway uspec prism retfound
say "3/5 Downloading PostgreSQL and Caddy"
docker pull --platform "$PLATFORM" postgres:16-alpine
docker pull --platform "$PLATFORM" caddy:2.8-alpine

say "4/5 Saving the images (compressed; several GB, several minutes)"
docker save "${IMAGES[@]}" | gzip -1 > "$WORK/images/$NAME-images.tar.gz"

{
  printf 'name=%s\n' "$NAME"
  printf 'commit=%s\n' "$COMMIT"
  printf 'image_tag=%s\n' "$TAG"
  printf 'profile=%s\n' "$PROFILE"
  printf 'platform=%s\n' "$PLATFORM"
  printf 'model_api_base_image=%s\n' "$BASE_IMAGE"
  printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'image=%s\n' "${IMAGES[@]}"
  printf 'model_weights=not included\n'
} > "$WORK/BUNDLE_INFO"

cat > "$WORK/README.txt" <<EOF
DR Screening hospital server: offline install bundle $NAME
Screening and research support only; not a diagnostic device.

This bundle holds the program and every Docker image. It does NOT hold the AI model files
(model weights are not in Git and are handed over separately by the DR Screening team).

On the hospital server (Ubuntu 22.04 or 24.04, NVIDIA RTX 3090, Docker, NVIDIA Container Toolkit):

  1. Check and unpack the bundle (in the folder you copied it to):
       sha256sum -c $NAME.tar.sha256
       sudo tar --no-same-owner -xf $NAME.tar -C /opt

  2. Copy the model files to /srv/dr-screening/models (or the folder you will name in step 3):
       uspec/                USPEC folder exactly as delivered: manifest.json, grading_state.pt and its four
                             source files
       PRISM-DR/             PRISM-DR source: a full git clone (with its .git folder) at the pinned revision,
                             unmodified
       prism/                PRISM-DR released weights folder (the "Final Models" tree) with its manifest.json
       RETFound/             RETFound source: a full git clone (with its .git folder) at the pinned revision,
                             unmodified
       retfound-aptos.pth    RETFound APTOS checkpoint file

  3. Run the installer and answer four questions:
       sudo bash /opt/$NAME/dr-screening/deployment/hospital-server/install.sh

How the model files are checked (nothing new is invented here; it is the program's own check):
  - The installer runs  python -m dr_support.setup_models --model <uspec|prism|retfound> --verify  inside each
    model container, and each model service runs the same check again every time it starts
    (MODEL_REQUIRE_VERIFIED_ASSETS=1). A service refuses to start when a file is missing or changed.
  - RETFound: git revision of the source and SHA-256 of the checkpoint, pinned in
    dr-screening/dr_support/providers/retfound.py
  - PRISM-DR: git revision of the source (dr_support/providers/prism.py) and the SHA-256 of all 21 weight files
    (dr_support/providers/prism_assets.json)
  - USPEC: SHA-256 of manifest.json, of grading_state.pt and of the four source files
    (dr_support/models/uspec_artifact.py)
  - The start check (deployment/dual-mode/bin/preflight.sh) also requires uspec/manifest.json,
    uspec/grading_state.pt, PRISM-DR/.git, prism/manifest.json, RETFound/.git and retfound-aptos.pth to exist.

The installer checks every file of this bundle against SHA256SUMS before loading the images.
More: dr-screening/deployment/hospital-server/IT_CHECKLIST.md
EOF

say "5/5 Writing checksums and packing one file"
(cd "$WORK" && find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -cf "$OUT/$NAME.tar" -C "$OUT" "$NAME"
(cd "$OUT" && sha256sum "$NAME.tar" > "$NAME.tar.sha256")
rm -rf "$WORK"

say ""
say "Done:"
say "  $OUT/$NAME.tar"
say "  $OUT/$NAME.tar.sha256   ($(cut -d' ' -f1 < "$OUT/$NAME.tar.sha256"))"
say "Carry both files to the hospital server, together with the model files (not included)."
