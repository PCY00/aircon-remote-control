#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_path="${project_root}/.venv/bin/python"
service_port="${AIRCON_PORT:-8001}"
host_address="${AIRCON_HOST:-}"

if [[ -z "${host_address}" ]]; then
    host_address="$(/usr/bin/tailscale ip -4)"
fi

if [[ -z "${host_address}" ]]; then
    echo "No Tailscale IPv4 address is available." >&2
    exit 1
fi

exec "${python_path}" -m uvicorn app.main:app \
    --host "${host_address}" \
    --port "${service_port}"
