#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
secret_source="${project_root}/runtime/zigbee/zigbee2mqtt/secret.yaml"
runtime_env="${project_root}/runtime/app.env"
unit_source="${project_root}/deploy/systemd/aircon-controller.service"
unit_target="${HOME}/.config/systemd/user/aircon-controller.service"
python_path="${project_root}/.venv/bin/python"

if [[ ! -f "${secret_source}" ]]; then
  echo "Zigbee2MQTT secret.yaml was not found." >&2
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

"${python_path}" -c "import paho.mqtt.client"

mkdir -p -- "$(dirname "${runtime_env}")" "$(dirname "${unit_target}")"

python3 - "${secret_source}" "${runtime_env}" <<'PY'
from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
values: dict[str, str] = {}

for source_line in source.read_text(encoding="utf-8").splitlines():
    line = source_line.strip()
    if not line or line.startswith("#") or ":" not in line:
        continue
    key, raw_value = line.split(":", 1)
    key = key.strip()
    raw_value = raw_value.strip()
    if key not in {"user", "password"}:
        continue
    if raw_value.startswith("'") and raw_value.endswith("'"):
        value = raw_value[1:-1].replace("''", "'")
    elif raw_value.startswith('"') and raw_value.endswith('"'):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"secret.yaml key {key!r} has invalid quoting") from exc
    else:
        raise SystemExit(f"secret.yaml key {key!r} must use a quoted scalar")
    if not isinstance(value, str) or not value:
        raise SystemExit(f"secret.yaml key {key!r} must be a non-empty string")
    values[key] = value

missing = {"user", "password"} - values.keys()
if missing:
    raise SystemExit("secret.yaml is missing required MQTT credentials")

environment = {
    "AIRCON_MQTT_ENABLED": "true",
    "AIRCON_MQTT_HOST": "127.0.0.1",
    "AIRCON_MQTT_PORT": "1883",
    "AIRCON_MQTT_USERNAME": values["user"],
    "AIRCON_MQTT_PASSWORD": values["password"],
    "AIRCON_MQTT_BASE_TOPIC": "zigbee2mqtt",
    "AIRCON_MQTT_CLIENT_ID": "aircon-controller",
    "AIRCON_MQTT_KEEPALIVE_SECONDS": "60",
}

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

echo "APP_MQTT_ENV=created mode=600"
echo "SERVICE_UNIT=updated"
echo "SERVICE_RESTART=completed"
