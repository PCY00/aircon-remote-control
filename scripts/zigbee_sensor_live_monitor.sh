#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/zigbee_sensor_live_monitor.sh}"
script_dir="$(cd -- "$(dirname -- "$script_source")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
secret_file="$project_root/runtime/zigbee/zigbee2mqtt/secret.yaml"
message_count="${1:-3}"
wait_seconds="${2:-180}"

if [[ ! -f "$secret_file" ]]; then
    echo "Zigbee runtime secret is missing." >&2
    exit 1
fi

mqtt_password="$(sed -n "s/^password: '\(.*\)'$/\1/p" "$secret_file")"
if [[ -z "$mqtt_password" ]]; then
    echo "Could not read the MQTT password from secret.yaml." >&2
    exit 1
fi

docker exec aircon-mosquitto mosquitto_sub \
    -h 127.0.0.1 -p 1883 \
    -u zigbee2mqtt -P "$mqtt_password" \
    -t zigbee2mqtt/sensor_temperature_01 \
    -t zigbee2mqtt/sensor_door_01 \
    -v -C "$message_count" -W "$wait_seconds" |
    while IFS= read -r message; do
        printf 'RECEIVED_AT=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message"
    done
