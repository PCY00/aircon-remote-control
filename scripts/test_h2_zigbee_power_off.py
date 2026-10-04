"""Safely preview or send one H2 Zigbee POWER_OFF through the Pi's MQTT broker.

Run on the Pi. No command is published unless --send is supplied. A lost
result is ambiguous: do not retry automatically, as IR may already have fired.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import select
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MODEL = "AIRCON_H2_IR_01"
CONTAINER = "aircon-mosquitto"
SECRET_FILE = Path(__file__).resolve().parents[1] / "runtime/zigbee/zigbee2mqtt/secret.yaml"


def mqtt_password() -> str:
    for line in SECRET_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("password: '") and line.endswith("'"):
            value = line[len("password: '") : -1]
            if value:
                return value
    raise RuntimeError("MQTT password unavailable in private runtime configuration")


def mqtt_command(program: str, password: str, *options: str) -> list[str]:
    return [
        "docker", "exec", CONTAINER, program,
        "-h", "127.0.0.1", "-p", "1883",
        "-u", "zigbee2mqtt", "-P", password, *options,
    ]


def retained_json(password: str, topic: str) -> object:
    result = subprocess.run(
        mqtt_command("mosquitto_sub", password, "-t", topic, "-C", "1", "-W", "10"),
        check=True, capture_output=True, text=True, timeout=15,
    )
    return json.loads(result.stdout)


def select_h2(devices: object) -> dict:
    if not isinstance(devices, list):
        raise RuntimeError("Zigbee device list is invalid")
    matches = [
        device for device in devices
        if isinstance(device, dict)
        and isinstance(device.get("definition"), dict)
        and device["definition"].get("model") == MODEL
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one supported H2, found {len(matches)}")
    device = matches[0]
    interviewed = (
        str(device.get("interview_state", "")).upper() == "SUCCESSFUL"
        or device.get("interview_completed") is True
    )
    if device.get("supported") is not True or not interviewed:
        raise RuntimeError("H2 is not supported or interview is incomplete")
    name = device.get("friendly_name")
    if not isinstance(name, str) or not name or "/" in name or "+" in name or "#" in name:
        raise RuntimeError("H2 MQTT friendly name is invalid")
    return device


def check_gateway(password: str) -> None:
    state = retained_json(password, "zigbee2mqtt/bridge/state")
    if state not in ({"state": "online"}, "online"):
        raise RuntimeError("Zigbee2MQTT is not online")
    info = retained_json(password, "zigbee2mqtt/bridge/info")
    if not isinstance(info, dict) or info.get("permit_join") is not False:
        raise RuntimeError("Zigbee permit-join must be closed")


def send_once(password: str, name: str) -> int:
    request_id = secrets.randbelow(0xFFFFFF) + 1
    topic = f"zigbee2mqtt/{name}"
    subscriber = subprocess.Popen(
        mqtt_command("mosquitto_sub", password, "-t", topic, "-R", "-W", "25"),
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        # Ensure the live-result subscription exists before the one allowed publish.
        time.sleep(0.5)
        if subscriber.poll() is not None:
            raise RuntimeError("Result subscription failed before publish")
        payload = json.dumps(
            {"ir_request": {"command": "POWER_OFF", "request_id": request_id}},
            separators=(",", ":"),
        )
        print(f"REQUEST_ID={request_id}", flush=True)
        subprocess.run(
            mqtt_command("mosquitto_pub", password, "-t", topic + "/set", "-m", payload),
            check=True, capture_output=True, text=True, timeout=10,
        )
        print("MQTT_PUBLISH_COUNT=1", flush=True)
        print("COMMAND=POWER_OFF", flush=True)
        deadline = time.monotonic() + 25
        pending = b""
        while time.monotonic() < deadline:
            if subscriber.stdout is None:
                break
            readable, _, _ = select.select(
                [subscriber.stdout], [], [], max(0, deadline - time.monotonic())
            )
            if not readable:
                break
            chunk = os.read(subscriber.stdout.fileno(), 65536)
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                try:
                    event = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                result = event.get("ir_result") if isinstance(event, dict) else None
                if not isinstance(result, dict) or result.get("request_id") != request_id:
                    continue
                status = result.get("status")
                print(f"MATCHED_IR_RESULT={status}", flush=True)
                if status == "sent":
                    print("IR_RESULT=RMT_COMPLETE_AC_STATE_NOT_VERIFIED", flush=True)
                    return 0
                if status in ("failed", "duplicate", "busy"):
                    return 2
        print("IR_RESULT=TIMEOUT_AMBIGUOUS_DO_NOT_RETRY", flush=True)
        return 3
    finally:
        if subscriber.poll() is None:
            subscriber.terminate()
        try:
            subscriber.wait(timeout=2)
        except subprocess.TimeoutExpired:
            subscriber.kill()
            subscriber.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true", help="publish exactly one POWER_OFF")
    args = parser.parse_args()
    password = mqtt_password()
    check_gateway(password)
    device = select_h2(retained_json(password, "zigbee2mqtt/bridge/devices"))
    print("KST=" + datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S"))
    print("GATEWAY=online", "PERMIT_JOIN=false", f"MODEL={MODEL}", "SUPPORTED=true", sep="\n")
    if not args.send:
        print("MODE=preview", "MQTT_PUBLISH_COUNT=0", sep="\n")
        return 0
    print("MODE=one-shot-send", flush=True)
    return send_once(password, device["friendly_name"])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        # A subprocess exception can embed -P <password> in its command line.
        print(f"ERROR={type(exc).__name__}; no command was retried", file=sys.stderr)
        sys.exit(1)
