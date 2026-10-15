#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/zigbee_sensor_live_monitor.sh}"
script_dir="$(cd -- "$(dirname -- "$script_source")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
secret_file="$project_root/runtime/zigbee/zigbee2mqtt/secret.yaml"
mosquitto_container="aircon-mosquitto"
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

# The broker password rides in the docker CLI environment (-e NAME propagates it
# without putting the value on the command line) and reaches the client through
# its default-options file, so it never appears in any host or container argv.
mqtt_client() {
    local client="$1"
    shift
    MQTT_PW="$mqtt_password" docker exec -e MQTT_PW "$mosquitto_container" sh -c '
        umask 077
        dir="$(mktemp -d)" || exit 1
        printf "%s %s\n" -P "$MQTT_PW" >"$dir/$0"
        XDG_CONFIG_HOME="$dir" "$0" -h 127.0.0.1 -p 1883 -u zigbee2mqtt "$@"
        rc=$?
        rm -rf -- "$dir"
        exit "$rc"
    ' "$client" "$@"
}

mqtt_sub() {
    mqtt_client mosquitto_sub "$@"
}

mqtt_sub \
    -t zigbee2mqtt/sensor_temperature_01 \
    -t zigbee2mqtt/sensor_door_01 \
    -v -C "$message_count" -W "$wait_seconds" |
    while IFS= read -r message; do
        printf 'RECEIVED_AT=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$message"
    done
