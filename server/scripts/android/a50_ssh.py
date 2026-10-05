"""Connect to the A50 using local, ignored connection details and a dedicated key."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection", type=Path, default=Path(".deploy/a50/connection.json")
    )
    parser.add_argument("command", nargs="?", help="One remote shell command; omit to log in.")
    args = parser.parse_args()
    if not args.connection.is_file():
        parser.error("Local connection file is missing; use the phone's verified values.")
    config = json.loads(args.connection.read_text(encoding="utf-8"))
    key = Path(config["identity_file"])
    known_hosts = Path(config["known_hosts_file"])
    if not key.is_file() or not known_hosts.is_file():
        parser.error("The dedicated key or verified host record is missing.")
    command = [
        "ssh",
        "-i", str(key),
        "-p", str(int(config["port"])),
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=10",
        f"{config['user']}@{config['host']}",
    ]
    if args.command is not None:
        command.append(args.command)
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
