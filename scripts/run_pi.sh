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

# The app builds its Host allowlist from AIRCON_HOST; export the resolved address
# so the Tailscale IP is accepted even when only run_pi.sh looked it up.
export AIRCON_HOST="${host_address}"

# The dashboard keeps an SSE stream open; without a limit a stop waits for it forever.
# --limit-concurrency bounds open connections (kiosk, phones, agent) with 503s.
exec "${python_path}" -m uvicorn app.main:app \
    --host "${host_address}" \
    --port "${service_port}" \
    --limit-concurrency 64 \
    --timeout-graceful-shutdown 5
