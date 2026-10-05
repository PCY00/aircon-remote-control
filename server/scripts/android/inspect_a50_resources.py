"""Read paired A50 resource state without changing apps or system settings."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from a50_adb import A50ADB

COMMANDS = {
    "resources": "date -u; uptime; cat /proc/meminfo; cat /proc/loadavg; cat /proc/stat",
    "top": "top -b -n 1 -m 25",
    "processes": "ps -A -o PID,PPID,USER,STAT,NAME",
    "memory": "dumpsys meminfo --oom",
    "cpu": "dumpsys cpuinfo",
    "battery": "dumpsys battery",
    "user_apps": "pm list packages -3",
    "enabled_apps": "pm list packages -e",
    "disabled_apps": "pm list packages -d",
    "system_apps": "pm list packages -s",
    "manager": (
        "am broadcast -a com.aircon.a50manager.STATUS "
        "-n com.aircon.a50manager/.StatusReceiver"
    ),
}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="before")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,40}", args.label):
        parser.error("Label must use lowercase letters, digits and hyphens.")
    client = A50ADB(Path(".deploy/a50/adb.json"))
    endpoint = client.connect(timeout=40)
    directory = Path("tmp/a50-resource-inspection") / (args.label + "-" + str(time.time_ns()))
    directory.mkdir(parents=True)
    results = {}
    for name, command in COMMANDS.items():
        response = client.run("-s", endpoint, "shell", command, timeout=60)
        output = (response.stdout + response.stderr).decode("utf-8", errors="replace")
        results[name] = {"command": command, "exit_code": response.returncode, "output": output}
        (directory / (name + ".txt")).write_text(output, encoding="utf-8")
        print(f"READ_ONLY_{name.upper()}_EXIT={response.returncode}", flush=True)
    (directory / "snapshot.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    Path("tmp/a50-resource-inspection/latest-" + args.label + ".json").write_text(
        json.dumps({"directory": str(directory)}, indent=2), encoding="utf-8"
    )
    print("PRIVATE_RESOURCE_SNAPSHOT_SAVED")
    return 1 if any(entry["exit_code"] for entry in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
