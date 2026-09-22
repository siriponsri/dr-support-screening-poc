#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
service_name="dr-support-model-api.service"
unit_source="$repo_root/deployment/$service_name"
unit_target="/etc/systemd/system/$service_name"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  exec sudo "$0" "$@"
fi

if [[ "$repo_root" != "/opt/dr-support-screening-poc" ]]; then
  echo "ERROR: install-service.sh expects the release at /opt/dr-support-screening-poc." >&2
  echo "Copy the clean release there, then rerun this script." >&2
  exit 1
fi

if ! id drsupport >/dev/null 2>&1; then
  useradd --system --home-dir /opt/dr-support-screening-poc --shell /usr/sbin/nologin drsupport
fi

install -d -m 0755 /etc/dr-support
if [[ ! -f /etc/dr-support/model-server.env ]]; then
  install -m 0640 "$repo_root/deployment/model-server.env.example" /etc/dr-support/model-server.env
  echo "Created /etc/dr-support/model-server.env; review it before starting the service."
fi
install -m 0644 "$unit_source" "$unit_target"
systemctl daemon-reload
systemctl enable "$service_name"
echo "Installed and enabled $service_name. Start it with: systemctl start $service_name"
