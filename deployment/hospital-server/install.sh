#!/usr/bin/env bash
# Guided installer for the DR Screening hospital local server (Ubuntu 22.04/24.04, one NVIDIA GPU, Docker).
#
#   sudo deployment/hospital-server/install.sh
#
# It checks the server, asks four questions, writes the private settings file with passwords made on this
# machine (never printed), loads the images from an offline bundle (or builds them), checks the model files,
# starts everything through bin/start.sh, creates the first administrator and prints the web address.
# Running it again is safe: the settings file and existing accounts are kept.
# Screening and research support only; not a diagnostic device.
set -euo pipefail

PKG=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$PKG/../.." && pwd)
DUAL=$REPO/deployment/dual-mode
TEMPLATE=$PKG/hospital.env.example
ENV_FILE=${DR_ENV_FILE:-/etc/dr-screening/hospital.env}
PROFILE=hospital-3090
GPU_REQUIRED="RTX 3090"          # deployment/dual-mode/bin/preflight.sh accepts only this card for the profile
APP_UID=10001                    # the web app container user (deployment/dual-mode/Dockerfile.review)
MODEL_SERVICES="uspec prism retfound"
MIN_RAM_GB=32
GOOD_RAM_GB=64
MIN_DOCKER_FREE_GB=40
MIN_DATA_FREE_GB=100

BUNDLE_DIR=""
SOURCE_COMMIT=""
IMAGE_TAG=""
SITE_ADDRESS=""
DATA_DIR=""
IMAGES_DIR=""
MODELS_DIR=""

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*"; }
fail() { printf '\nStopped: %s\n' "$*" >&2; exit 1; }

# ask VAR "question" "default": one plain question; Enter keeps the default.
ask() {
  local var=$1 question=$2 default=$3 answer=""
  printf '\n%s\n  Press Enter for: %s\n> ' "$question" "$default"
  read -r answer || answer=""
  printf -v "$var" '%s' "${answer:-$default}"
}

# confirm_yes "question": true only when the operator types exactly yes.
confirm_yes() {
  local answer=""
  printf '\n%s\n  Type yes to continue, anything else to skip: ' "$1"
  read -r answer || answer=""
  [ "$answer" = "yes" ]
}

# 48 hexadecimal characters from the kernel random source. Only ever used inside write_env_file.
new_secret() { od -An -N24 -tx1 /dev/urandom | tr -d ' \n'; }

template_value() { sed -n "s/^$1=//p" "$TEMPLATE" | head -n1; }
bundle_value() { sed -n "s/^$1=//p" "$BUNDLE_DIR/BUNDLE_INFO" | head -n1; }
env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | head -n1; }
compose() {
  docker compose -f "$DUAL/compose.yml" -f "$PKG/compose.override.yml" --profile "$PROFILE" \
    --env-file "$ENV_FILE" "$@"
}
images_for_tag() {
  local tag=$1
  printf '%s\n' "dr-screening/review:$tag" "dr-screening/model-gateway:$tag" "dr-screening/uspec-api:$tag" \
    "dr-screening/prism-api:$tag" "dr-screening/retfound-api:$tag" postgres:16-alpine caddy:2.8-alpine
}
free_gb() { df -Pk "$1" 2>/dev/null | awk 'NR == 2 {print int($4 / 1048576)}'; }
nearest_existing() { local p=$1; while [ ! -e "$p" ]; do p=$(dirname "$p"); done; printf '%s' "$p"; }

# ------------------------------------------------------------------------------------------- 1. prerequisites

install_docker() {
  confirm_yes "Docker Engine is missing. Install it now from Docker's official Ubuntu repository (needs internet)?" \
    || return 1
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "$(. /etc/os-release && printf '%s' "$VERSION_CODENAME")" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

install_toolkit() {
  confirm_yes "NVIDIA Container Toolkit is missing. Install it now from NVIDIA's official repository (needs internet)?" \
    || return 1
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update
  apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
}

check_prerequisites() {
  step "1/7 Checking this server"
  [ "$(id -u)" -eq 0 ] || fail "run the installer with sudo:  sudo bash $0"

  local os_id="" os_version=""
  if [ -r /etc/os-release ]; then
    os_id=$(. /etc/os-release && printf '%s' "${ID:-}")
    os_version=$(. /etc/os-release && printf '%s' "${VERSION_ID:-}")
  fi
  case "$os_id:$os_version" in
    ubuntu:22.04|ubuntu:24.04) say "  OK  Ubuntu $os_version" ;;
    *) warn "this installer is tested for Ubuntu 22.04 or 24.04 only (found: ${os_id:-unknown} ${os_version})."
       confirm_yes "Continue anyway?" || fail "use Ubuntu Server 22.04 or 24.04 LTS." ;;
  esac
  [ "$(uname -m)" = "x86_64" ] || fail "the images are built for x86_64 (64-bit Intel/AMD) servers; found $(uname -m)."

  command -v nvidia-smi >/dev/null 2>&1 || fail "the NVIDIA driver is not installed (nvidia-smi not found).
  Fix: sudo apt-get update && sudo ubuntu-drivers install   then restart the server and run this installer again."
  local gpu
  gpu=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -n1 || true)
  [ -n "$gpu" ] || fail "nvidia-smi found no GPU. Check that the card is seated and the driver matches it, then restart."
  case "$gpu" in
    *"$GPU_REQUIRED"*) say "  OK  GPU: $gpu" ;;
    *) fail "the hospital profile is qualified only for an NVIDIA $GPU_REQUIRED (found: $gpu).
  Ask the DR Screening team to qualify a profile for this card before installing." ;;
  esac

  if ! command -v docker >/dev/null 2>&1; then
    install_docker || fail "Docker Engine is required. Install it as described at https://docs.docker.com/engine/install/ubuntu/ and run this installer again."
  fi
  docker info >/dev/null 2>&1 || fail "Docker is installed but not running. Fix: sudo systemctl start docker"
  docker compose version >/dev/null 2>&1 || fail "the Docker Compose plugin is missing. Fix: sudo apt-get install docker-compose-plugin"
  say "  OK  Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null) with Compose $(docker compose version --short 2>/dev/null)"

  if ! command -v nvidia-ctk >/dev/null 2>&1 && ! docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
    install_toolkit || fail "NVIDIA Container Toolkit is required. Install it as described at https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html and run this installer again."
  fi
  say "  OK  NVIDIA Container Toolkit"

  local ram_gb cores docker_root docker_free
  ram_gb=$(awk '/^MemTotal:/ {print int(($2 + 524288) / 1048576)}' /proc/meminfo)
  cores=$(nproc)
  if [ "$ram_gb" -lt "$MIN_RAM_GB" ]; then
    warn "only ${ram_gb} GB RAM (at least $MIN_RAM_GB GB needed, $GOOD_RAM_GB GB recommended)."
    confirm_yes "Continue anyway?" || fail "add memory first."
  elif [ "$ram_gb" -lt "$GOOD_RAM_GB" ]; then
    say "  OK  RAM ${ram_gb} GB (works; $GOOD_RAM_GB GB recommended)"
  else
    say "  OK  RAM ${ram_gb} GB"
  fi
  [ "$cores" -ge 8 ] && say "  OK  $cores CPU cores" || warn "only $cores CPU cores (12 to 16 recommended)."
  docker_root=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || printf '/var/lib/docker')
  docker_free=$(free_gb "$(nearest_existing "$docker_root")")
  if [ "${docker_free:-0}" -lt "$MIN_DOCKER_FREE_GB" ]; then
    warn "only ${docker_free:-0} GB free for Docker images in $docker_root (at least $MIN_DOCKER_FREE_GB GB needed)."
    confirm_yes "Continue anyway?" || fail "free disk space first."
  else
    say "  OK  ${docker_free} GB free for Docker images"
  fi
  if command -v ss >/dev/null 2>&1; then
    local listener
    listener=$(ss -Hltnp 'sport = :443' 2>/dev/null || true)
    if [ -n "$listener" ] && ! printf '%s' "$listener" | grep -q docker-proxy; then
      warn "another program already listens on port 443; the web app needs that port."
      printf '%s\n' "$listener"
      confirm_yes "Continue anyway?" || fail "stop the other program that uses port 443."
    fi
  fi
}

# ---------------------------------------------------------------------------------- 2. version and settings

detect_version() {
  if [ -f "$REPO/../BUNDLE_INFO" ] && [ -f "$REPO/../SHA256SUMS" ]; then
    BUNDLE_DIR=$(cd "$REPO/.." && pwd)
    SOURCE_COMMIT=$(bundle_value commit)
    IMAGE_TAG=$(bundle_value image_tag)
    say "  Offline bundle: $BUNDLE_DIR"
  elif command -v git >/dev/null 2>&1 && git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD >/dev/null 2>&1; then
    SOURCE_COMMIT=$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)
    IMAGE_TAG=git-${SOURCE_COMMIT:0:12}
    say "  Project folder from Git (images will be built here; this needs internet)"
  else
    fail "run the installer from an offline bundle or from a folder downloaded with git clone."
  fi
  [[ "$SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "the version of this copy is unknown (no 40-character commit)."
  [[ "$IMAGE_TAG" =~ ^[A-Za-z0-9_.-]{1,64}$ ]] || fail "the image tag of this copy is not valid."
  say "  Version: $IMAGE_TAG"
}

valid_path() { [[ "$1" =~ ^/[A-Za-z0-9._/-]+$ ]] && [[ "$1" != *..* ]]; }

ask_questions() {
  local default_site
  default_site=$(hostname -I 2>/dev/null | awk '{print $1}')
  [ -n "$default_site" ] || default_site=$(hostname)
  say ""
  say "Four questions. Press Enter to accept the suggestion in each."
  ask SITE_ADDRESS "Question 1 of 4: the address hospital users will type in the browser
  (a name from your DNS, for example dr-screening.example.test, or this server's IP address)" "$default_site"
  [[ "$SITE_ADDRESS" =~ ^[A-Za-z0-9.-]{1,253}$ ]] || fail "the address may contain only letters, digits, dots and dashes."
  ask IMAGES_DIR "Question 2 of 4: the folder that holds the retinal images (the app only reads it)" \
    /srv/dr-screening/images
  ask DATA_DIR "Question 3 of 4: the folder for app data and backups (use the data disk, not the system disk)" \
    /srv/dr-screening/data
  ask MODELS_DIR "Question 4 of 4: the folder where the AI model files are (or will be) copied" \
    /srv/dr-screening/models
  local p
  for p in "$IMAGES_DIR" "$DATA_DIR" "$MODELS_DIR"; do
    valid_path "$p" || fail "use a full folder path with letters, digits, dots, dashes and slashes only (got: $p)."
  done
}

write_env_file() {
  local base_image tmp
  base_image=$(template_value MODEL_API_BASE_IMAGE)
  [ -n "$base_image" ] || fail "MODEL_API_BASE_IMAGE is missing from $TEMPLATE."
  mkdir -p "$(dirname "$ENV_FILE")"
  tmp=$(umask 077 && mktemp "$ENV_FILE.XXXXXX")
  (
    umask 077
    {
      printf '%s\n' "# Private settings for the DR Screening hospital server, written by install.sh."
      printf '%s\n' "# Root only (mode 600). Never copy into Git, e-mail or chat. Passwords were made on this server."
      printf 'DUAL_MODE_GPU_PROFILE=%s\n' "$PROFILE"
      printf 'DR_SCREENING_SOURCE_COMMIT=%s\n' "$SOURCE_COMMIT"
      printf 'DR_SCREENING_IMAGE_TAG=%s\n' "$IMAGE_TAG"
      printf 'MODEL_API_BASE_IMAGE=%s\n' "$base_image"
      printf 'USPEC_GPU_ID=0\nPRISM_GPU_ID=0\nRETFOUND_GPU_ID=0\n'
      printf 'USPEC_MODEL_DIR=%s\n' "$MODELS_DIR/uspec"
      printf 'PRISM_SOURCE=%s\n' "$MODELS_DIR/PRISM-DR"
      printf 'PRISM_WEIGHTS=%s\n' "$MODELS_DIR/prism"
      printf 'RETFOUND_SOURCE=%s\n' "$MODELS_DIR/RETFound"
      printf 'RETFOUND_WEIGHTS=%s\n' "$MODELS_DIR/retfound-aptos.pth"
      printf 'DR_SUPPORT_POSTGRES_DB=dr_support\nDR_SUPPORT_POSTGRES_USER=dr_support\n'
      printf 'DR_SUPPORT_POSTGRES_PASSWORD=%s\n' "$(new_secret)"
      printf 'REMOTE_MODEL_TOKEN=%s\n' "$(new_secret)"
      printf 'DR_DATA_DIR=%s\n' "$DATA_DIR"
      printf 'DR_IMAGES_DIR=%s\n' "$IMAGES_DIR"
      printf 'DR_SITE_ADDRESS=%s\n' "$SITE_ADDRESS"
      printf 'DR_HTTPS_BIND=0.0.0.0\n'
      printf 'DR_SUPPORT_REFERRAL_HOSTS=\n'
    } > "$tmp"
  )
  chmod 600 "$tmp"
  mv -f "$tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

settings() {
  step "2/7 Settings"
  detect_version
  if [ -f "$ENV_FILE" ]; then
    chmod 600 "$ENV_FILE"
    say "  Keeping your existing settings: $ENV_FILE"
    local current
    current=$(env_value DR_SCREENING_SOURCE_COMMIT)
    if [ "$current" != "$SOURCE_COMMIT" ]; then
      say "  Installed version: $(env_value DR_SCREENING_IMAGE_TAG)   This copy: $IMAGE_TAG"
      if confirm_yes "Update the server to this copy? A database backup is taken first if the server is running."; then
        if compose ps --status running --services 2>/dev/null | grep -qx postgres; then
          DR_ENV_FILE="$ENV_FILE" sh "$PKG/bin/backup.sh"
        fi
        sed -i -e "s/^DR_SCREENING_SOURCE_COMMIT=.*/DR_SCREENING_SOURCE_COMMIT=$SOURCE_COMMIT/" \
          -e "s/^DR_SCREENING_IMAGE_TAG=.*/DR_SCREENING_IMAGE_TAG=$IMAGE_TAG/" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        say "  Settings now point to $IMAGE_TAG (passwords unchanged)."
      else
        IMAGE_TAG=$(env_value DR_SCREENING_IMAGE_TAG)
        SOURCE_COMMIT=$current
        say "  Keeping the installed version $IMAGE_TAG."
      fi
    fi
  else
    ask_questions
    write_env_file
    say "  Settings saved (passwords made on this server, not shown): $ENV_FILE"
  fi
  grep -v '^[[:space:]]*#' "$ENV_FILE" | grep -q 'REPLACE' && fail "$ENV_FILE still has REPLACE values; fix or remove it."
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  IMAGE_TAG=$DR_SCREENING_IMAGE_TAG
}

# ------------------------------------------------------------------------------------ 3. folders and models

MISSING_MODELS=""

folders() {
  step "3/7 Folders"
  local d
  for d in config state output backups; do mkdir -p "$DR_DATA_DIR/$d"; done
  chown -R "$APP_UID:$APP_UID" "$DR_DATA_DIR/config" "$DR_DATA_DIR/state" "$DR_DATA_DIR/output"
  chmod 750 "$DR_DATA_DIR/config" "$DR_DATA_DIR/state" "$DR_DATA_DIR/output"
  chmod 700 "$DR_DATA_DIR/backups"
  [ -d "$DR_IMAGES_DIR" ] || { mkdir -p "$DR_IMAGES_DIR"; chmod 755 "$DR_IMAGES_DIR"; }
  say "  Data:   $DR_DATA_DIR"
  say "  Images: $DR_IMAGES_DIR (mounted read-only; originals are never changed)"
  if [ -n "$(find "$DR_IMAGES_DIR" -maxdepth 1 -type f ! -perm -o=r -print -quit 2>/dev/null)" ]; then
    warn "some image files are not readable by the app (it runs as user $APP_UID)."
    say "  Fix (read permission only, files are not changed): sudo chmod -R o+rX $DR_IMAGES_DIR"
  fi
  local free
  free=$(free_gb "$DR_DATA_DIR")
  [ "${free:-0}" -ge "$MIN_DATA_FREE_GB" ] || warn "only ${free:-0} GB free for data in $DR_DATA_DIR (plan for several hundred GB)."

  MISSING_MODELS=""
  local p
  for p in "$USPEC_MODEL_DIR/manifest.json" "$USPEC_MODEL_DIR/grading_state.pt" "$PRISM_SOURCE/.git" \
           "$PRISM_WEIGHTS/manifest.json" "$RETFOUND_SOURCE/.git" "$RETFOUND_WEIGHTS"; do
    [ -e "$p" ] || MISSING_MODELS="$MISSING_MODELS
    $p"
  done
  if [ -n "$MISSING_MODELS" ]; then
    warn "AI model files are not in place yet. Missing:$MISSING_MODELS"
  else
    say "  Model files found in $(dirname "$USPEC_MODEL_DIR")"
  fi
}

# ------------------------------------------------------------------------------------------------ 4. images

images_present() {
  local image
  while IFS= read -r image; do
    docker image inspect "$image" >/dev/null 2>&1 || return 1
  done < <(images_for_tag "$IMAGE_TAG")
}

images() {
  step "4/7 Programs (Docker images)"
  if images_present; then
    say "  Images for $IMAGE_TAG are already on this server."
  elif [ -n "$BUNDLE_DIR" ] && [ "$(bundle_value image_tag)" = "$IMAGE_TAG" ]; then
    say "  Checking the bundle files (a few minutes)..."
    (cd "$BUNDLE_DIR" && sha256sum --quiet -c SHA256SUMS) \
      || fail "the bundle is damaged or changed (checksum mismatch). Copy it again from the original."
    local archive
    for archive in "$BUNDLE_DIR"/images/*.tar.gz; do
      [ -f "$archive" ] || fail "no image archive found in $BUNDLE_DIR/images."
      say "  Loading $(basename "$archive") (several minutes)..."
      docker load -i "$archive"
    done
    images_present || fail "the bundle does not hold every image for $IMAGE_TAG."
  else
    say "  Building the images here (needs internet; 20 to 40 minutes the first time)..."
    compose build review gateway uspec prism retfound
    docker pull postgres:16-alpine
    docker pull caddy:2.8-alpine
  fi

  say "  Checking that containers can use the GPU..."
  docker run --rm --gpus all --entrypoint nvidia-smi "dr-screening/uspec-api:$IMAGE_TAG" -L >/dev/null 2>&1 \
    || fail "containers cannot use the GPU. Fix: sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
  then run this installer again."
  say "  OK  containers can use the GPU"
}

verify_models() {
  if [ -n "$MISSING_MODELS" ]; then
    say ""
    say "The settings and programs are ready, but the AI model files are missing:$MISSING_MODELS"
    say ""
    say "Copy them as described in IT_CHECKLIST.md (section: Model files), then run again:"
    say "  sudo bash $0"
    exit 2
  fi
  step "5/7 Checking the model files against the pinned versions"
  local service
  for service in $MODEL_SERVICES; do
    say "  $service..."
    compose run --rm --no-deps -T "$service" python -m dr_support.setup_models --model "$service" --verify >/dev/null \
      || fail "the $service model files do not match the pinned version. Copy them again from the original source.
  Details: sudo docker compose -f $DUAL/compose.yml -f $PKG/compose.override.yml --profile $PROFILE --env-file $ENV_FILE run --rm --no-deps $service python -m dr_support.setup_models --model $service --verify"
  done
  say "  OK  all model files match"
}

# ------------------------------------------------------------------------------------------ 5. start and wait

service_health() { compose ps --format '{{.Service}} {{.Health}}' 2>/dev/null | awk -v s="$1" '$1 == s {print $2}'; }

start_and_wait() {
  step "6/7 Starting"
  DR_ENV_FILE="$ENV_FILE" sh "$PKG/bin/start.sh"
  say "  Waiting for the web app and the three AI services (up to 10 minutes)..."
  local i service all_ok
  for i in $(seq 1 120); do
    all_ok=1
    for service in review gateway uspec prism retfound; do
      [ "$(service_health "$service")" = "healthy" ] || all_ok=0
    done
    [ "$all_ok" -eq 1 ] && break
    sleep 5
  done
  if [ "$all_ok" -ne 1 ]; then
    DR_ENV_FILE="$ENV_FILE" sh "$PKG/bin/status.sh" || true
    [ "$(service_health review)" = "healthy" ] || fail "the web app did not become healthy. See: sudo docker logs \$(sudo docker ps -qf name=review)"
    warn "the web app runs, but an AI service is not healthy yet; AI shows as not available until it is."
  else
    say "  OK  all services healthy"
  fi
  if command -v curl >/dev/null 2>&1; then
    local url="https://$DR_SITE_ADDRESS/health" resolve=()
    [[ "$DR_SITE_ADDRESS" =~ ^[0-9.]+$ ]] || resolve=(--resolve "$DR_SITE_ADDRESS:443:127.0.0.1")
    for i in $(seq 1 20); do
      curl -fsk -o /dev/null --max-time 5 "${resolve[@]}" "$url" && break
      sleep 3
    done
    curl -fsk -o /dev/null --max-time 5 "${resolve[@]}" "$url" \
      && say "  OK  HTTPS answers at https://$DR_SITE_ADDRESS/" \
      || warn "HTTPS did not answer yet at https://$DR_SITE_ADDRESS/ (check: sudo docker compose logs https)."
  fi
}

# ------------------------------------------------------------------------------------ 6. administrator, extras

first_admin() {
  step "7/7 Administrator account"
  if [ -s "$DR_DATA_DIR/config/pilot-users.json" ]; then
    say "  Accounts already exist (kept). Reset one later with: sudo sh $PKG/bin/create-admin.sh <username>"
    return 0
  fi
  local user=""
  ask user "Username for the first administrator (lowercase)" admin
  [[ "$user" =~ ^[a-z0-9._-]{1,64}$ ]] || fail "use lowercase letters, digits, dots, dashes or underscores."
  say "Choose a temporary password (at least 8 letters and digits). Typing is hidden."
  say "The administrator must choose a new one at the first sign-in."
  DR_ENV_FILE="$ENV_FILE" sh "$PKG/bin/create-admin.sh" "$user" \
    || fail "the account was not created. Run again and choose a longer password with letters and digits."
}

extras() {
  local cert="$DR_DATA_DIR/dr-screening-https-root.crt"
  if compose exec -T https cat /data/caddy/pki/authorities/local/root.crt > "$cert.tmp" 2>/dev/null && [ -s "$cert.tmp" ]; then
    mv -f "$cert.tmp" "$cert"
    chmod 644 "$cert"
  else
    rm -f "$cert.tmp"
  fi
  local cron=/etc/cron.d/dr-screening-backup
  if [ -f "$cron" ]; then
    # After an update from a new folder, point the existing nightly backup at this copy's script.
    grep -qF "$PKG/bin/backup.sh" "$cron" || { write_backup_cron "$cron"; say "  Nightly backup now uses: $PKG"; }
  elif confirm_yes "Add a nightly database backup at 02:30 (keeps the last 14 in $DR_DATA_DIR/backups)?"; then
    write_backup_cron "$cron"
    say "  Nightly backup added: $cron"
  fi
}

write_backup_cron() {
  printf '%s\n' "# DR Screening nightly database backup (written by install.sh)" \
    "30 2 * * * root DR_ENV_FILE=$ENV_FILE /bin/sh $PKG/bin/backup.sh >> /var/log/dr-screening-backup.log 2>&1" > "$1"
  chmod 644 "$1"
}

finish() {
  say ""
  say "Done. DR Screening is running."
  say ""
  say "  Web address for hospital PCs:  https://$DR_SITE_ADDRESS/app/"
  say "  Settings (private):            $ENV_FILE"
  say "  Data and backups:              $DR_DATA_DIR"
  if [ -f "$DR_DATA_DIR/dr-screening-https-root.crt" ]; then
    say "  HTTPS certificate to trust:    $DR_DATA_DIR/dr-screening-https-root.crt"
    say "    (install it on hospital PCs as a trusted root, for example by group policy, to stop the browser warning)"
  fi
  say ""
  say "Next steps:"
  say "  1. Allow port 443 from the hospital network only (hospital firewall). Docker opens the port itself,"
  say "     so a ufw rule on this server alone does not limit it."
  say "  2. Sign in as the administrator, choose a new password, then add the doctors on the Admin page."
  say "  3. Health: sudo sh $PKG/bin/status.sh    Stop: sudo sh $PKG/bin/stop.sh    Backup now: sudo sh $PKG/bin/backup.sh"
  say ""
  say "Screening and research support only; not a diagnostic device."
}

main() {
  umask 077
  say "DR Screening hospital server installer"
  check_prerequisites
  settings
  folders
  images
  verify_models
  start_and_wait
  first_admin
  extras
  finish
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
