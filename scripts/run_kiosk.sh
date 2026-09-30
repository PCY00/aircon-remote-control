#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_dir="${project_root}/runtime/kiosk/chromium"
cache_dir="${project_root}/runtime/kiosk/cache"
service_port="${AIRCON_PORT:-8001}"

has_connected_display() {
    local status_file
    shopt -s nullglob
    for status_file in /sys/class/drm/card*-*/status; do
        if [[ "$(<"${status_file}")" == "connected" ]]; then
            return 0
        fi
    done
    return 1
}

for executable in /usr/bin/cage /usr/bin/chromium /usr/bin/curl /usr/bin/tailscale; do
    if [[ ! -x "${executable}" ]]; then
        echo "Required kiosk executable is missing: ${executable}" >&2
        exit 1
    fi
done

mkdir -p "${profile_dir}" "${cache_dir}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-${cache_dir}}"
export XDG_SESSION_TYPE=wayland

if ! has_connected_display; then
    echo "No connected DRM display. Waiting for HDMI/DSI display..."
fi
until has_connected_display; do
    sleep 5
done
echo "Display detected. Preparing dashboard kiosk."

tailscale_ipv4=""
until [[ -n "${tailscale_ipv4}" ]]; do
    tailscale_ipv4="$(/usr/bin/tailscale ip -4 2>/dev/null | head -n 1 || true)"
    if [[ -z "${tailscale_ipv4}" ]]; then
        echo "Waiting for a Tailscale IPv4 address..."
        sleep 3
    fi
done

dashboard_url="http://${tailscale_ipv4}:${service_port}/?kiosk=1"
health_url="http://${tailscale_ipv4}:${service_port}/health"
until /usr/bin/curl --fail --silent --show-error --max-time 3 "${health_url}" >/dev/null; do
    echo "Waiting for the dashboard service on port ${service_port}..."
    sleep 3
done
echo "Dashboard is healthy. Starting Chromium kiosk."

exec /usr/bin/cage -d -s -- /usr/bin/chromium \
    --kiosk \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-component-update \
    --disable-features=Translate,MediaRouter \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --password-store=basic \
    --ozone-platform=wayland \
    --enable-features=UseOzonePlatform \
    --touch-events=enabled \
    --user-data-dir="${profile_dir}" \
    "${dashboard_url}"
