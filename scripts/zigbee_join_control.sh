#!/usr/bin/env bash
set -Eeuo pipefail

script_source="${BASH_SOURCE[0]:-$PWD/zigbee_join_control.sh}"
script_dir="$(cd -- "$(dirname -- "$script_source")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
secret_file="$project_root/runtime/zigbee/zigbee2mqtt/secret.yaml"
mosquitto_container="aircon-mosquitto"

usage() {
    cat <<'EOF'
Usage:
  zigbee_join_control.sh status
  zigbee_join_control.sh open [30-254]
  zigbee_join_control.sh close

Opening permit-join changes the Zigbee network state. Use it for one device at a
time and close it immediately after the interview succeeds or fails.
EOF
}

if [[ ! -f "$secret_file" ]]; then
    echo "Zigbee runtime secret is missing. Run setup_zigbee_stack.sh first." >&2
    exit 1
fi
if ! docker inspect "$mosquitto_container" >/dev/null 2>&1; then
    echo "Mosquitto container is unavailable: $mosquitto_container" >&2
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

print_status() {
    mqtt_sub -t zigbee2mqtt/bridge/info -C 1 -W 10 | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
permit_join = str(bool(payload.get("permit_join"))).lower()
end = payload.get("permit_join_end")
permit_join_end = end if end is not None else "none"
print("PERMIT_JOIN=" + permit_join)
print("PERMIT_JOIN_END=" + str(permit_join_end))
'
}

request_permit_join() {
    local seconds="$1"
    local response_file
    local subscriber_pid
    response_file="$(mktemp)"
    trap 'rm -f -- "$response_file"' EXIT

    mqtt_sub \
        -t zigbee2mqtt/bridge/response/permit_join \
        -C 1 -W 10 >"$response_file" &
    subscriber_pid=$!
    sleep 0.25
    mqtt_pub \
        -t zigbee2mqtt/bridge/request/permit_join \
        -m "{\"time\":$seconds,\"device\":\"coordinator\"}"
    if ! wait "$subscriber_pid"; then
        echo "Timed out waiting for the permit_join response." >&2
        return 1
    fi
    if ! grep -Eq '"status"[[:space:]]*:[[:space:]]*"ok"' "$response_file"; then
        echo "Zigbee2MQTT rejected the permit_join request:" >&2
        cat "$response_file" >&2
        return 1
    fi
    rm -f -- "$response_file"
    trap - EXIT

    if (( seconds == 0 )); then
        echo "PERMIT_JOIN_REQUEST=closed"
    else
        echo "PERMIT_JOIN_REQUEST=open"
        echo "PERMIT_JOIN_SECONDS=$seconds"
        echo "PERMIT_JOIN_TARGET=coordinator"
    fi
    print_status
}

command="${1:-}"
case "$command" in
    status)
        print_status
        ;;
    open)
        duration="${2:-180}"
        if [[ ! "$duration" =~ ^[0-9]+$ ]] || (( duration < 30 || duration > 254 )); then
            echo "Duration must be an integer from 30 to 254 seconds." >&2
            exit 2
        fi
        request_permit_join "$duration"
        ;;
    close)
        request_permit_join 0
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
