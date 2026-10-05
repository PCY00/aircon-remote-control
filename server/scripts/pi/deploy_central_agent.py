"""Deploy only the independent Pi relay; default is a read-only remote comparison."""

from __future__ import annotations

import argparse
import base64
import hashlib
import sys
from pathlib import Path

from pi_session import PiSession


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    files = {
        name: (Path("services/pi-central-agent") / name).read_bytes().replace(b"\r\n", b"\n")
        for name in ("agent.py", "aircon-central-agent.service")
    }
    checksum = hashlib.sha256()
    for name, data in sorted(files.items()):
        checksum.update(name.encode() + b"\0" + data + b"\0")
    payload = {
        "release": checksum.hexdigest()[:16],
        "files": {name: base64.b64encode(data).decode() for name, data in files.items()},
    }
    script = Path("scripts/pi/apply_central_agent.py").read_text(encoding="utf-8")
    script += "\ninstall(" + repr(payload) + ", apply=" + repr(args.apply) + ")\n"
    record = PiSession("pi-agent-deploy-" + ("apply" if args.apply else "preview"))
    for name, data in files.items():
        record.log("SOURCE_SHA256=" + hashlib.sha256(data).hexdigest() + " " + name)
    record.run(
        "python3 -",
        data=script.encode(),
        timeout=90,
        label="python3 - < independent Pi agent checked manifest ["
        + ("apply" if args.apply else "preview")
        + "]",
    )


if __name__ == "__main__":
    main()
