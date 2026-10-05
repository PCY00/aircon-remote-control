"""Use the existing, user-confirmed Pi SSH target and retain sanitized evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/android"))
from a50_record import PhoneSession  # noqa: E402


class PiSession(PhoneSession):
    def command(self):
        path = ROOT / ".deploy/pi-central-agent/connection.json"
        if not path.is_file():
            raise RuntimeError(
                "Pi connection missing; follow the reader guide to save your verified target"
            )
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        key, known = Path(config["identity_file"]), Path(config["known_hosts_file"])
        if not key.is_file() or not known.is_file():
            raise RuntimeError("Pi key or verified host record missing; no connection attempted")
        return [
            "ssh",
            "-i",
            str(key),
            "-p",
            str(int(config["port"])),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "UserKnownHostsFile=" + str(known),
            "-o",
            "ConnectTimeout=10",
            config["user"] + "@" + config["host"],
        ]
