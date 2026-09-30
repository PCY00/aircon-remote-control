#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/rename_zigbee_devices.sh}"
script_dir="$(cd -- "$(dirname -- "$script_source")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
secret_file="$project_root/runtime/zigbee/zigbee2mqtt/secret.yaml"
mosquitto_container="aircon-mosquitto"
response_file=""
subscriber_pid=""

cleanup() {
    if [[ -n "$subscriber_pid" ]]; then
        kill "$subscriber_pid" 2>/dev/null || true
    fi
    if [[ -n "$response_file" ]]; then
        rm -f -- "$response_file"
    fi
}
trap cleanup EXIT

if [[ ! -f "$secret_file" ]]; then
    echo "Zigbee runtime secret is missing." >&2
    exit 1
fi

mqtt_password="$(sed -n "s/^password: '\(.*\)'$/\1/p" "$secret_file")"
if [[ -z "$mqtt_password" ]]; then
    echo "Could not read the MQTT password from secret.yaml." >&2
    exit 1
fi

mqtt_sub() {
    docker exec "$mosquitto_container" mosquitto_sub \
        -h 127.0.0.1 -p 1883 \
        -u zigbee2mqtt -P "$mqtt_password" "$@"
}

mqtt_pub() {
    docker exec "$mosquitto_container" mosquitto_pub \
        -h 127.0.0.1 -p 1883 \
        -u zigbee2mqtt -P "$mqtt_password" "$@"
}

devices_json="$(mqtt_sub -t zigbee2mqtt/bridge/devices -C 1 -W 10)"

resolve_friendly_name() {
    local model="$1"
    local target="$2"

    python3 -c '
import json
import sys

model, target = sys.argv[1:]
devices = json.load(sys.stdin)
matches = [
    item
    for item in devices
    if item.get("type") != "Coordinator"
    and (item.get("definition") or {}).get("model") == model
]
if len(matches) != 1:
    raise SystemExit(f"Expected one {model} device, found {len(matches)}")

target_owners = [
    item
    for item in devices
    if item.get("type") != "Coordinator"
    and item.get("friendly_name") == target
]
if target_owners and target_owners[0] is not matches[0]:
    raise SystemExit(f"Target friendly name already belongs to another device: {target}")

print(matches[0].get("friendly_name", ""))
' "$model" "$target" <<<"$devices_json"
}

rename_device() {
    local model="$1"
    local target="$2"
    local current
    local payload
    local response

    current="$(resolve_friendly_name "$model" "$target")"
    if [[ "$current" == "$target" ]]; then
        echo "RENAME_${model}=already_named"
        return
    fi

    payload="$(python3 -c '
import json
import sys

print(json.dumps({"from": sys.argv[1], "to": sys.argv[2]}))
' "$current" "$target")"

    response_file="$(mktemp)"
    mqtt_sub \
        -t zigbee2mqtt/bridge/response/device/rename \
        -C 1 -W 10 >"$response_file" &
    subscriber_pid=$!
    sleep 0.25
    mqtt_pub \
        -t zigbee2mqtt/bridge/request/device/rename \
        -m "$payload"
    wait "$subscriber_pid"
    subscriber_pid=""
    response="$(<"$response_file")"
    rm -f -- "$response_file"
    response_file=""

    python3 -c '
import json
import sys

target = sys.argv[1]
response = json.load(sys.stdin)
if response.get("status") != "ok":
    raise SystemExit("Rename failed: " + str(response.get("error", "unknown error")))
if (response.get("data") or {}).get("to") != target:
    raise SystemExit("Rename response target did not match")
' "$target" <<<"$response"

    echo "RENAME_${model}=ok"
}

rename_device TH01 sensor_temperature_01
rename_device TS0203 sensor_door_01

devices_json="$(mqtt_sub -t zigbee2mqtt/bridge/devices -C 1 -W 10)"
python3 -c '
import json
import sys

expected = {
    "TH01": "sensor_temperature_01",
    "TS0203": "sensor_door_01",
}
devices = json.load(sys.stdin)
actual = {
    (item.get("definition") or {}).get("model"): item.get("friendly_name")
    for item in devices
    if item.get("type") != "Coordinator"
}
for model, friendly_name in expected.items():
    if actual.get(model) != friendly_name:
        raise SystemExit(f"Friendly name verification failed for {model}")
    print(f"VERIFY_{model}_FRIENDLY_NAME={friendly_name}")
' <<<"$devices_json"

echo "ZIGBEE_DEVICE_RENAME_STATUS=success"
