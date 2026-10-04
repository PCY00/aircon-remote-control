#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/zigbee_device_summary.sh}"
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

docker exec "$mosquitto_container" mosquitto_sub \
    -h 127.0.0.1 -p 1883 \
    -u zigbee2mqtt -P "$mqtt_password" \
    -t zigbee2mqtt/bridge/devices -C 1 -W 10 | python3 -c '
import json
import re
import sys

payload = json.load(sys.stdin)
devices = [item for item in payload if item.get("type") != "Coordinator"]
print("DEVICE_COUNT=" + str(len(devices)))
for index, device in enumerate(devices, start=1):
    definition = device.get("definition") or {}
    friendly_name = str(device.get("friendly_name", "unknown"))
    if re.fullmatch(r"0x[0-9a-fA-F]{16}", friendly_name):
        friendly_name = "[REDACTED_IEEE]"
    interview_state = str(device.get("interview_state", "")).upper()
    interview_completed = interview_state == "SUCCESSFUL" or bool(
        device.get("interview_completed")
    )
    print("DEVICE_" + str(index) + "_TYPE=" + str(device.get("type", "unknown")))
    print("DEVICE_" + str(index) + "_MODEL=" + str(definition.get("model", "unknown")))
    print("DEVICE_" + str(index) + "_VENDOR=" + str(definition.get("vendor", "unknown")))
    print("DEVICE_" + str(index) + "_FRIENDLY_NAME=" + friendly_name)
    print(
        "DEVICE_"
        + str(index)
        + "_INTERVIEW_COMPLETED="
        + str(interview_completed).lower()
    )
    supported = device.get("supported")
    if not isinstance(supported, bool):
        supported = bool(definition)
    print("DEVICE_" + str(index) + "_SUPPORTED=" + str(supported).lower())
'
