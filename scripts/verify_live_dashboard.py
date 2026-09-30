"""Read-only HTTP smoke check for a deployed dashboard; never send IR commands.

Run on the Pi, or pipe this file to its virtualenv Python. Output intentionally
omits addresses, credentials, sensor identifiers and event payloads for blog use.
"""

from __future__ import annotations

import json
import subprocess
import time
from urllib.request import urlopen


def main() -> None:
    address = subprocess.check_output(["tailscale", "ip", "-4"], text=True).strip()
    base = f"http://{address}:8001"

    def get(path: str) -> object:
        with urlopen(base + path, timeout=10) as response:
            assert response.status == 200, path
            return json.load(response)

    health = get("/health")
    assert health["status"] == "ok"
    print("HEALTH=ok", flush=True)
    schema = get("/openapi.json")
    print(f"API_VERSION={schema['info']['version']}", flush=True)
    assert schema["info"]["version"] == "0.7.0"
    status = get("/api/v1/sensors/status")
    print(f"MQTT_CONNECTED={str(status.get('connected')).lower()}", flush=True)
    assert status.get("connected") is True
    sensors = get("/api/v1/sensors")["items"]
    print(f"SENSOR_COUNT={len(sensors)}", flush=True)
    print("SENSOR_KINDS=" + ",".join(sorted({s['kind'] for s in sensors})), flush=True)
    assert {s["kind"] for s in sensors} >= {"door_contact", "temperature_humidity"}
    zigbee = get("/api/v1/zigbee/devices")["items"]
    print(f"ZIGBEE_DEVICE_COUNT={len(zigbee)}", flush=True)
    join = get("/api/v1/zigbee/join")
    print(f"PERMIT_JOIN={str(join.get('permit_join')).lower()}", flush=True)
    rules = get("/api/v1/automations")["items"]
    assert len(rules) == 1
    rule = rules[0]
    assert rule["id"] == "door-open-aircon-warning"
    print(f"AUTOMATION_COUNT={len(rules)}", flush=True)
    print(f"RULE_ENABLED={str(rule['enabled']).lower()}", flush=True)
    print(f"RULE_DELAY_SECONDS={rule['delay_seconds']}", flush=True)
    print(f"WARNING_ACTIVE={str(rule['state']['warning_active']).lower()}", flush=True)
    history = get("/api/v1/automations/events?limit=20")["items"]
    print(f"AUTOMATION_EVENT_COUNT={len(history)}", flush=True)
    with urlopen(base + "/?kiosk=1", timeout=10) as response:
        html = response.read().decode("utf-8")
    assert "/static/sensors.js?v=20260908-1" in html
    assert "/static/automations.js?v=20260908-1" in html
    print("UI_ASSET_REVISION=20260908-1", flush=True)
    print("KIOSK_CURSOR_CSS=" + str('html[data-kiosk="true"]' in html).lower(), flush=True)

    ready = False
    heartbeat = False
    live_count = 0
    with urlopen(base + "/api/v1/events", timeout=20) as response:
        assert response.headers.get_content_type() == "text/event-stream"
        print("SSE_HTTP=200 text/event-stream", flush=True)
        started = time.monotonic()
        while time.monotonic() - started < 20:
            line = response.readline().decode("utf-8").strip()
            if line.startswith("data:"):
                event = json.loads(line[5:].strip())
                if event.get("type") == "stream.ready":
                    ready = True
                elif event.get("type") == "sensor.updated":
                    live_count += 1
            elif line == ": keep-alive":
                heartbeat = True
                break
    print(f"SSE_READY={str(ready).lower()}", flush=True)
    print(f"SSE_KEEPALIVE={str(heartbeat).lower()}", flush=True)
    print(f"SSE_SENSOR_EVENTS_OBSERVED={live_count}", flush=True)
    assert ready
    assert heartbeat or live_count > 0
    print("IR_COMMANDS_SENT=0", flush=True)
    print("DASHBOARD_SMOKE=passed", flush=True)


if __name__ == "__main__":
    main()
