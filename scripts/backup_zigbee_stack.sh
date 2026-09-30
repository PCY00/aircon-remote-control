#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
compose_dir="$project_root/deploy/zigbee"
runtime_dir="$project_root/runtime/zigbee"
env_file="$runtime_dir/stack.env"
backup_dir="$runtime_dir/backups"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$backup_dir/zigbee-stack-$timestamp.tar.gz"

if [[ ! -f "$env_file" ]]; then
    echo "Zigbee runtime configuration is missing." >&2
    exit 1
fi

compose=(docker compose --env-file "$env_file" --file "$compose_dir/compose.yaml")
mkdir -p -- "$backup_dir"
chmod 700 -- "$backup_dir"

for service in mosquitto zigbee2mqtt; do
    if [[ -z "$("${compose[@]}" ps --status running -q "$service")" ]]; then
        echo "Required service is not running: $service" >&2
        exit 1
    fi
done

restart_needed=false
cleanup() {
    if [[ "$restart_needed" == true ]]; then
        "${compose[@]}" start mosquitto zigbee2mqtt >/dev/null
    fi
}
trap cleanup EXIT

restart_needed=true
"${compose[@]}" stop zigbee2mqtt mosquitto >/dev/null

tar -czf "$backup_path" \
    --exclude='./backups' \
    -C "$runtime_dir" \
    ./stack.env ./mosquitto ./zigbee2mqtt
chmod 600 -- "$backup_path"
sha256sum -- "$backup_path"

"${compose[@]}" start mosquitto zigbee2mqtt >/dev/null
restart_needed=false

echo "BACKUP_STATUS=success"
echo "BACKUP_CONTAINS_SECRETS=true"
