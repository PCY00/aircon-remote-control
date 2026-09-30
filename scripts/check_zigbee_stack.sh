#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
compose_dir="$project_root/deploy/zigbee"
runtime_dir="$project_root/runtime/zigbee"
env_file="$runtime_dir/stack.env"
secret_file="$runtime_dir/zigbee2mqtt/secret.yaml"

if [[ ! -f "$env_file" ]] || [[ ! -f "$secret_file" ]]; then
    echo "Zigbee runtime configuration is missing. Run setup_zigbee_stack.sh first." >&2
    exit 1
fi

mqtt_password="$(sed -n "s/^password: '\(.*\)'$/\1/p" "$secret_file")"
if [[ -z "$mqtt_password" ]]; then
    echo "Could not read the MQTT password from secret.yaml." >&2
    exit 1
fi

compose=(docker compose --env-file "$env_file" --file "$compose_dir/compose.yaml")

echo "[containers]"
"${compose[@]}" ps

z2m_started_at="$(docker inspect -f '{{.State.StartedAt}}' aircon-zigbee2mqtt)"
deadline=$((SECONDS + 60))
z2m_ready=false
z2m_current_logs=""
while (( SECONDS < deadline )); do
    z2m_current_logs="$(docker logs --since "$z2m_started_at" aircon-zigbee2mqtt 2>&1)"
    if grep -Fq 'Zigbee2MQTT started!' <<<"$z2m_current_logs"; then
        z2m_ready=true
        break
    fi
    sleep 2
done

echo
echo "[zigbee2mqtt current-start milestones]"
printf '%s\n' "$z2m_current_logs" | \
    grep -E 'Starting Zigbee2MQTT|Serialport opened|Coordinator firmware version|Connected to MQTT server|bridge/state|Zigbee2MQTT started|error:|warning:' || true
if [[ "$z2m_ready" != true ]]; then
    echo "The current Zigbee2MQTT container did not become ready within 60 seconds." >&2
    exit 1
fi

echo
echo "[mqtt bridge state]"
bridge_state="$(docker exec aircon-mosquitto mosquitto_sub \
    -h 127.0.0.1 -p 1883 \
    -u zigbee2mqtt -P "$mqtt_password" \
    -t zigbee2mqtt/bridge/state -C 1 -W 10)"
printf '%s\n' "$bridge_state"

echo
echo "[host listeners]"
for port in 1883 8080; do
    addresses="$(ss -H -lnt | awk -v suffix=":$port" '$4 ~ suffix "$" {print $4}')"
    if [[ -z "$addresses" ]]; then
        echo "PORT_${port}_LISTENING=false"
        exit 1
    fi
    if printf '%s\n' "$addresses" | grep -Evq '^127\.0\.0\.1:'; then
        echo "PORT_${port}_LOOPBACK_ONLY=false"
        exit 1
    fi
    echo "PORT_${port}_LOOPBACK_ONLY=true"
done

echo
echo "[existing application]"
aircon_address="$(tailscale ip -4 | head -n 1)"
curl -fsS "http://$aircon_address:8001/health"
echo

if [[ "$bridge_state" != *'"state":"online"'* ]] && [[ "$bridge_state" != "online" ]]; then
    echo "MQTT bridge state is not online." >&2
    exit 1
fi

echo "ZIGBEE_STACK_STATUS=success"
