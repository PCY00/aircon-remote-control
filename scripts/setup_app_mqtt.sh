#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_env="${project_root}/runtime/app.env"
mosquitto_dir="${project_root}/runtime/zigbee/mosquitto"
passwords_file="${mosquitto_dir}/passwords"
unit_source="${project_root}/deploy/systemd/aircon-controller.service"
unit_target="${HOME}/.config/systemd/user/aircon-controller.service"
python_path="${project_root}/.venv/bin/python"
mosquitto_image="eclipse-mosquitto:2.1.2-alpine"
mosquitto_container="aircon-mosquitto"
# The web app gets its own broker identity; the ACL in deploy/zigbee/mosquitto/acl.conf
# limits it to reading reports and sending set / permit_join requests.
app_mqtt_user="aircon-controller"

if [[ ! -f "${passwords_file}" ]]; then
  echo "Mosquitto password file was not found. Run setup_zigbee_stack.sh first." >&2
  exit 1
fi
if [[ ! -f "${unit_source}" ]]; then
  echo "The aircon-controller systemd unit template was not found." >&2
  exit 1
fi
if [[ ! -x "${python_path}" ]]; then
  echo "The project virtualenv Python was not found." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker is unavailable to the current user; it is needed to hash the broker password." >&2
  exit 1
fi

"${python_path}" -c "import paho.mqtt.client"

mkdir -p -- "$(dirname "${runtime_env}")" "$(dirname "${unit_target}")"

# Keep the app's existing password when app.env already holds its own identity;
# otherwise mint a new one. The value only ever travels through environment
# variables and mode-600 files, never through a command line.
app_password="$("${python_path}" - "${runtime_env}" "${app_mqtt_user}" <<'PY'
from __future__ import annotations

import shlex
import sys
from pathlib import Path

target = Path(sys.argv[1])
user = sys.argv[2]
values: dict[str, str] = {}
if target.is_file():
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        parts = shlex.split(raw_value)
        values[key.strip()] = parts[0] if parts else ""
if values.get("AIRCON_MQTT_USERNAME") == user and values.get("AIRCON_MQTT_PASSWORD"):
    print(values["AIRCON_MQTT_PASSWORD"])
PY
)"
if [[ -z "${app_password}" ]]; then
  app_password="$(openssl rand -hex 24)"
fi

# Hash the password with mosquitto_passwd -U on a private staging file so the
# plain text never appears in `docker run` arguments, then replace the user's line.
umask 077
staging_name=".passwords.${app_mqtt_user}.$$"
staging_file="${mosquitto_dir}/${staging_name}"
cleanup() {
  rm -f -- "${staging_file}" "${passwords_file}.tmp"
}
trap cleanup EXIT
printf '%s:%s\n' "${app_mqtt_user}" "${app_password}" >"${staging_file}"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "${mosquitto_dir}:/work" \
  "${mosquitto_image}" \
  mosquitto_passwd -U "/work/${staging_name}"
hashed_line="$(grep -m1 "^${app_mqtt_user}:" "${staging_file}")"
if [[ -z "${hashed_line}" ]] || [[ "${hashed_line}" == "${app_mqtt_user}:${app_password}" ]]; then
  echo "mosquitto_passwd did not produce a hashed entry for ${app_mqtt_user}." >&2
  exit 1
fi
{
  grep -v "^${app_mqtt_user}:" "${passwords_file}" || true
  printf '%s\n' "${hashed_line}"
} >"${passwords_file}.tmp"
# Rewrite the existing file in place: Mosquitto bind-mounts this single file, so a
# rename would leave the running container (and its SIGHUP reload) on the old inode.
cat -- "${passwords_file}.tmp" >"${passwords_file}"
rm -f -- "${passwords_file}.tmp"
chmod 600 -- "${passwords_file}"
rm -f -- "${staging_file}"

# Mosquitto re-reads password_file and acl_file on SIGHUP without dropping Zigbee2MQTT.
if [[ "$(docker inspect -f '{{.State.Running}}' "${mosquitto_container}" 2>/dev/null || true)" == "true" ]]; then
  docker kill --signal=HUP "${mosquitto_container}" >/dev/null
  echo "MOSQUITTO_RELOAD=signalled"
else
  echo "MOSQUITTO_RELOAD=skipped_container_not_running"
fi

APP_MQTT_USERNAME="${app_mqtt_user}" APP_MQTT_PASSWORD="${app_password}" \
  "${python_path}" - "${runtime_env}" <<'PY'
from __future__ import annotations

import os
import shlex
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
environment = {
    "AIRCON_MQTT_ENABLED": "true",
    "AIRCON_MQTT_HOST": "127.0.0.1",
    "AIRCON_MQTT_PORT": "1883",
    "AIRCON_MQTT_USERNAME": os.environ["APP_MQTT_USERNAME"],
    "AIRCON_MQTT_PASSWORD": os.environ["APP_MQTT_PASSWORD"],
    "AIRCON_MQTT_BASE_TOPIC": "zigbee2mqtt",
    "AIRCON_MQTT_CLIENT_ID": "aircon-controller",
    "AIRCON_MQTT_KEEPALIVE_SECONDS": "60",
}
# Keep unrelated settings (e.g. AIRCON_ALLOWED_HOSTS) that already live in app.env.
preserved: dict[str, str] = {}
if target.is_file():
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        if key.strip() not in environment:
            preserved[key.strip()] = raw_value

descriptor, temporary_name = tempfile.mkstemp(
    dir=target.parent,
    prefix=".app.env.",
    text=True,
)
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        for key, value in environment.items():
            output.write(f"{key}={shlex.quote(value)}\n")
        for key, raw_value in preserved.items():
            output.write(f"{key}={raw_value}\n")
    os.replace(temporary_name, target)
except BaseException:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
    raise
PY

chmod 600 -- "${runtime_env}"
install -m 0644 -- "${unit_source}" "${unit_target}"
systemctl --user daemon-reload
systemctl --user restart aircon-controller

echo "APP_MQTT_USER=${app_mqtt_user}"
echo "APP_MQTT_ENV=created mode=600"
echo "SERVICE_UNIT=updated"
echo "SERVICE_RESTART=completed"
