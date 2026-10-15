"""Connect to the A50 using local, ignored connection details and a dedicated key."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def ssh_command(connection: Path, command: str | None = None) -> list[str]:
    """Build the verified-host SSH command so callers can run ssh as their direct child."""
    config = json.loads(connection.read_text(encoding="utf-8"))
    key = Path(config["identity_file"])
    known_hosts = Path(config["known_hosts_file"])
    if not key.is_file() or not known_hosts.is_file():
        raise ValueError("The dedicated key or verified host record is missing.")
    # A login or host starting with "-" would be read by ssh as an option, not a destination.
    user, host = str(config["user"]), str(config["host"])
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", user) or not re.fullmatch(
        r"[A-Za-z0-9_:][A-Za-z0-9_.:-]*", host
    ):
        raise ValueError("The saved user or host is not a plain ssh destination.")
    arguments = [
        "ssh",
        "-i", str(key),
        "-p", str(int(config["port"])),
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "ConnectTimeout=10",
        # Detect a peer that disappears mid-session instead of waiting for TCP to give up.
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2",
        f"{user}@{host}",
    ]
    if command is not None:
        arguments.append(command)
    return arguments


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connection", type=Path, default=Path(".deploy/a50/connection.json")
    )
    parser.add_argument("command", nargs="?", help="One remote shell command; omit to log in.")
    args = parser.parse_args()
    if not args.connection.is_file():
        parser.error("Local connection file is missing; use the phone's verified values.")
    try:
        command = ssh_command(args.connection, args.command)
    except ValueError as error:
        parser.error(str(error))
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
