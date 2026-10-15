"""Use the existing, user-confirmed Pi SSH target and retain sanitized evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/android"))
from a50_record import PhoneSession  # noqa: E402

# A leading '-' would turn the target into an ssh option; the same rule applies to any user regex.
SSH_USER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
SSH_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]*")
# ssh stderr names the target even when the remote step never runs; captures are committed.
GENERIC_REDACTIONS = (
    (r"\b[A-Za-z0-9][A-Za-z0-9.-]*\.ts\.net\b", "[REDACTED_TAILNET_HOST]"),
    (r"\bfd7a:115c:a1e0:[0-9A-Fa-f:]+", "[REDACTED_ADDRESS]"),
    (r"(?<=Identity file )\S+", "[REDACTED_LOCAL_PATH]"),
    (r'(?<=Load key ")[^"]+', "[REDACTED_LOCAL_PATH]"),
    (r"[A-Za-z0-9_][A-Za-z0-9_.-]*@(?=\[REDACTED_)", "[REDACTED_PI_USER]@"),
)


def connection_file():
    return ROOT / ".deploy/pi-central-agent/connection.json"


def load_connection():
    path = connection_file()
    if not path.is_file():
        raise RuntimeError(
            "Pi connection missing; follow the reader guide to save your verified target"
        )
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if (not isinstance(config.get("user"), str) or not SSH_USER.fullmatch(config["user"])
            or not isinstance(config.get("host"), str) or not SSH_HOST.fullmatch(config["host"])
            or not 1 <= int(config["port"]) <= 65535):
        raise RuntimeError(
            "Pi connection user/host/port is not a plain ssh target; no connection attempted"
        )
    return config


class PiSession(PhoneSession):
    def redact_pi(self, value):
        path = connection_file()
        if path.is_file():
            c = json.loads(path.read_text(encoding="utf-8-sig"))
            for private, label in (
                (c["user"] + "@" + c["host"], "[REDACTED_PI_USER]@[REDACTED_PI_HOST]"),
                (c["host"], "[REDACTED_PI_HOST]"),
                (c["user"], "[REDACTED_PI_USER]"),
            ):
                value = re.sub(r"(?<![\w.-])" + re.escape(private) + r"(?![\w.-])", label, value)
            for private in (str(c["identity_file"]), str(c["known_hosts_file"])):
                for variant in (private, private.replace("\\", "/"), private.replace("\\", "\\\\")):
                    value = value.replace(variant, "[REDACTED_LOCAL_PATH]")
        for pattern, label in GENERIC_REDACTIONS:
            value = re.sub(pattern, label, value)
        return value

    def log(self, value):
        # PhoneSession.log() only knows the A50 values; the Pi target is removed here first.
        super().log(self.redact_pi(value))

    def command(self):
        config = load_connection()
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
