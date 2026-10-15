"""Save the reader's verified local connection details without replacing existing files."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path


def save_new(paths_and_values):
    if any(path.exists() for path, _ in paths_and_values):
        raise RuntimeError("Settings already exist; no existing file was replaced")
    for path, value in paths_and_values:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")


def known_connection(args):
    # A user starting with "-" would be read by ssh as an option; require a plain login name.
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.host) or not re.fullmatch(
        r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args.user
    ):
        raise ValueError("Use a host and user you confirmed on your own device")
    if not 1 <= args.port <= 65535:
        raise ValueError("Invalid SSH port")
    key, known = args.identity_file.resolve(), args.known_hosts_file.resolve()
    if not key.is_file() or not known.is_file():
        raise ValueError("Create your key and confirm the SSH host fingerprint first")
    lookup = args.host if args.port == 22 else "[" + args.host + "]:" + str(args.port)
    found = subprocess.run(
        ["ssh-keygen", "-F", lookup, "-f", str(known)], capture_output=True, timeout=10
    )
    if found.returncode or not found.stdout.strip():
        raise ValueError("Host fingerprint has not been saved in this known_hosts file")
    return dict(
        host=args.host,
        port=args.port,
        user=args.user,
        identity_file=str(key),
        known_hosts_file=str(known),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="device", required=True)
    for device, port in [("phone", 8022), ("pi", 22)]:
        command = commands.add_parser(device)
        command.add_argument("--host", required=True)
        command.add_argument("--user", required=True)
        command.add_argument("--port", type=int, default=port)
        command.add_argument("--identity-file", type=Path, required=True)
        command.add_argument("--known-hosts-file", type=Path, required=True)
        command.add_argument("--root", type=Path, default=Path.cwd())
        if device == "phone":
            command.add_argument("--adb", type=Path, required=True)
            command.add_argument("--endpoint", required=True)
            command.add_argument("--model", default="SM-A505N")
    args = parser.parse_args()
    directory = (
        args.root.resolve() / ".deploy" / ("a50" if args.device == "phone" else "pi-central-agent")
    )
    targets = [directory / "connection.json"]
    if args.device == "phone":
        targets.append(directory / "adb.json")
    if any(path.exists() for path in targets):
        parser.error("Settings already exist; keep them. No connection or settings changed")
    # Subprocess errors print the full command, which holds the private address
    # and the local tool path, so report only a generic message.
    try:
        connection = known_connection(args)
    except (OSError, subprocess.SubprocessError):
        parser.error("ssh-keygen could not read the known_hosts file")
    files = [(targets[0], connection)]
    if args.device == "phone":
        try:
            address, port = args.endpoint.rsplit(":", 1)
            valid_endpoint = (
                str(ipaddress.IPv4Address(address)) == args.host and 1 <= int(port) <= 65535
            )
        except ValueError:
            valid_endpoint = False
        if not valid_endpoint:
            parser.error("Use the connection port and the same phone Wi-Fi address")
        adb = args.adb.resolve()
        if not adb.is_file():
            parser.error("ADB file not found")
        values = []
        try:
            for prop in ["ro.serialno", "ro.product.model"]:
                result = subprocess.run(
                    [str(adb), "-s", args.endpoint, "shell", "getprop", prop],
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                values.append(result.stdout.decode("utf-8").strip())
        except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
            parser.error(
                "ADB could not read the phone; reconnect wireless debugging and use the new port"
            )
        serial, model = values
        if not re.fullmatch(r"[A-Za-z0-9_-]{4,128}", serial) or model != args.model:
            parser.error("The connected device does not match the model you selected")
        files.append(
            (
                targets[1],
                dict(
                    adb_path=str(adb),
                    device_serial=serial,
                    model=model,
                    mdns_prefix="adb-" + serial + "-",
                    cached_endpoint=args.endpoint,
                    ssh_recovery_enabled=False,
                ),
            )
        )
    save_new(files)
    print("READER_CONNECTION_SAVED=TRUE PRIVATE_VALUES=NOT_PRINTED EXISTING_FILES=NOT_REPLACED")


if __name__ == "__main__":
    main()
