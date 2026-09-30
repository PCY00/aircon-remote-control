#!/usr/bin/env bash
set -Eeuo pipefail

if (( EUID != 0 )); then
    echo "Run this script with sudo: sudo scripts/install_zigbee_host.sh" >&2
    exit 1
fi

target_user="${SUDO_USER:-air}"
if ! id "$target_user" >/dev/null 2>&1; then
    echo "Target user does not exist: $target_user" >&2
    exit 1
fi

echo "INSTALL_TARGET_USER=$target_user"
echo "INSTALL_PACKAGES=docker.io docker-compose"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose
systemctl enable --now docker.service
usermod -aG docker "$target_user"

docker --version
docker compose version
systemctl is-enabled docker.service
systemctl is-active docker.service

echo "HOST_INSTALL_STATUS=success"
echo "Reconnect the SSH session before running setup_zigbee_stack.sh."
