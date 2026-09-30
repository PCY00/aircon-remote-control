#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/zigbee_sensor_state_summary.sh}"
script_dir="$(cd -- "$(dirname -- "$script_source")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
secret_file="$project_root/runtime/zigbee/zigbee2mqtt/secret.yaml"
mosquitto_container="aircon-mosquitto"

if [[ ! -f "$secret_file" ]]; then
    echo "Zigbee runtime secret is missing." >&2
    exit 1
fi

mqtt_password="$(sed -n "s/^password: '\(.*\)'$/\1/p" "$secret_file")"
if [[ -z "$mqtt_password" ]]; then
    echo "Could not read the MQTT password from secret.yaml." >&2
    exit 1
fi

summarize_device() {
    local device_name="$1"
    local device_kind="$2"
    local payload

    if ! payload="$(docker exec "$mosquitto_container" mosquitto_sub \
        -h 127.0.0.1 -p 1883 \
        -u zigbee2mqtt -P "$mqtt_password" \
        -t "zigbee2mqtt/$device_name" -C 1 -W 3 2>/dev/null)"; then
        echo "DEVICE=$device_name"
        echo "PAYLOAD_AVAILABLE=false"
        return
    fi

    SENSOR_PAYLOAD="$payload" python3 - "$device_name" "$device_kind" <<'PY'
import json
import os
import sys

device_name, device_kind = sys.argv[1:]
payload = json.loads(os.environ["SENSOR_PAYLOAD"])

print(f"DEVICE={device_name}")
if device_kind == "door":
    contact = payload.get("contact")
    state = "closed" if contact is True else "open" if contact is False else "unknown"
    print(f"STATE={state}")
    for field in ("battery", "battery_low", "tamper", "voltage", "linkquality"):
        if field in payload:
            print(f"{field.upper()}={payload[field]}")
else:
    for field in ("temperature", "humidity", "battery", "voltage", "linkquality"):
        if field in payload:
            print(f"{field.upper()}={payload[field]}")

if "last_seen" in payload:
    print(f"LAST_SEEN={payload['last_seen']}")
PY
}

summarize_device sensor_temperature_01 temperature_humidity
summarize_device sensor_door_01 door
