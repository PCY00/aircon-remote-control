#!/usr/bin/env bash
set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
compose_dir="$project_root/deploy/zigbee"
runtime_dir="$project_root/runtime/zigbee"
env_file="$runtime_dir/stack.env"
z2m_data_dir="$runtime_dir/zigbee2mqtt"
mosquitto_dir="$runtime_dir/mosquitto"
mosquitto_image="eclipse-mosquitto:2.1.2-alpine"

if ! docker info >/dev/null 2>&1; then
    echo "Docker is unavailable to the current user. Reconnect after the docker group change." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is unavailable." >&2
    exit 1
fi
if [[ ! -f "$compose_dir/compose.yaml" ]]; then
    echo "Compose file is missing: $compose_dir/compose.yaml" >&2
    exit 1
fi

shopt -s nullglob
adapters=(/dev/serial/by-id/usb-Silicon_Labs_CP2102N_USB_to_UART_Bridge_Controller_*-if00-port0)
shopt -u nullglob
if (( ${#adapters[@]} != 1 )); then
    echo "Expected exactly one CP2102N Zigbee adapter, found ${#adapters[@]}." >&2
    exit 1
fi
adapter_path="${adapters[0]}"
if [[ ! -c "$(readlink -f -- "$adapter_path")" ]]; then
    echo "Adapter does not resolve to a character device." >&2
    exit 1
fi

host_uid="$(id -u)"
host_gid="$(id -g)"
dialout_gid="$(getent group dialout | cut -d: -f3)"
if [[ -z "$dialout_gid" ]] || ! id -nG | tr ' ' '\n' | grep -qx dialout; then
    echo "The current user must belong to the dialout group." >&2
    exit 1
fi

umask 077
mkdir -p -- "$z2m_data_dir" "$mosquitto_dir/data" "$runtime_dir/backups"

if [[ ! -f "$env_file" ]]; then
    cat >"$env_file" <<EOF
HOST_UID=$host_uid
HOST_GID=$host_gid
DIALOUT_GID=$dialout_gid
TZ=Asia/Seoul
ZIGBEE_RUNTIME_DIR=$runtime_dir
ZIGBEE_ADAPTER_PATH=$adapter_path
EOF
fi

if [[ ! -f "$z2m_data_dir/configuration.yaml" ]]; then
    cp -- "$compose_dir/zigbee2mqtt/configuration.example.yaml" "$z2m_data_dir/configuration.yaml"
fi

if [[ ! -f "$z2m_data_dir/secret.yaml" ]]; then
    mqtt_password="$(openssl rand -hex 24)"
    frontend_token="$(openssl rand -hex 32)"
    network_key="$(od -An -N16 -tu1 /dev/urandom | awk '
        BEGIN { printf "["; separator = "" }
        { for (i = 1; i <= NF; i++) { printf "%s%s", separator, $i; separator = ", " } }
        END { print "]" }
    ')"
    cat >"$z2m_data_dir/secret.yaml" <<EOF
server: 'mqtt://mosquitto:1883'
user: 'zigbee2mqtt'
password: '$mqtt_password'
network_key: $network_key
frontend_auth_token: '$frontend_token'
EOF
else
    mqtt_password="$(sed -n "s/^password: '\(.*\)'$/\1/p" "$z2m_data_dir/secret.yaml")"
    if [[ -z "$mqtt_password" ]]; then
        echo "Could not read the existing MQTT password from secret.yaml." >&2
        exit 1
    fi
fi

docker pull "$mosquitto_image"
if [[ ! -f "$mosquitto_dir/passwords" ]]; then
    docker run --rm \
        --user "$host_uid:$host_gid" \
        --volume "$mosquitto_dir:/work" \
        "$mosquitto_image" \
        mosquitto_passwd -b -c /work/passwords zigbee2mqtt "$mqtt_password"
fi

chmod 700 -- "$runtime_dir" "$z2m_data_dir" "$mosquitto_dir" "$mosquitto_dir/data" "$runtime_dir/backups"
chmod 600 -- "$env_file" "$z2m_data_dir/configuration.yaml" "$z2m_data_dir/secret.yaml" "$mosquitto_dir/passwords"

docker compose --env-file "$env_file" --file "$compose_dir/compose.yaml" config --quiet
docker compose --env-file "$env_file" --file "$compose_dir/compose.yaml" pull
docker compose --env-file "$env_file" --file "$compose_dir/compose.yaml" up -d

echo "ZIGBEE_RUNTIME_CREATED=$runtime_dir"
echo "ZIGBEE_ADAPTER_CONFIGURED=by-id"
echo "ZIGBEE_CHANNEL=20"
echo "ZIGBEE_STACK_START_REQUESTED=true"
