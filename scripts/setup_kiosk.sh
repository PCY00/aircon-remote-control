#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
kiosk_user="${AIRCON_KIOSK_USER:-air}"
kiosk_group="$(id -gn "${kiosk_user}")"
unit_source="${project_root}/deploy/systemd/aircon-kiosk.service"
unit_target="/etc/systemd/system/aircon-kiosk.service"

if [[ ! -f "${unit_source}" ]]; then
    echo "Missing systemd unit template: ${unit_source}" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    cage \
    chromium \
    chromium-sandbox \
    fonts-noto-cjk

chown "${kiosk_user}:${kiosk_group}" "${project_root}/scripts/run_kiosk.sh"
chmod 0755 "${project_root}/scripts/run_kiosk.sh"
chmod 0755 "${project_root}/scripts/setup_kiosk.sh"
install -o root -g root -m 0644 "${unit_source}" "${unit_target}"
install -d -o "${kiosk_user}" -g "${kiosk_group}" -m 0750 \
    "${project_root}/runtime/kiosk" \
    "${project_root}/runtime/kiosk/chromium" \
    "${project_root}/runtime/kiosk/cache"

systemctl daemon-reload
systemctl enable aircon-kiosk.service
systemctl restart aircon-kiosk.service

echo "Kiosk packages installed and aircon-kiosk.service enabled."
