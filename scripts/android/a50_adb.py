"""Rediscover the paired A50 over mDNS and verify its identity before any command."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path


class ConnectionError(RuntimeError):
    """The configured phone could not be safely selected."""


def validate_endpoint(value: str) -> str:
    address, port = value.rsplit(":", 1)
    ipaddress.IPv4Address(address)
    if not 1 <= int(port) <= 65535:
        raise ValueError("Invalid port")
    return f"{address}:{int(port)}"


def discover_endpoints(output: str, prefix: str) -> list[str]:
    endpoints: set[str] = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        name, kind, endpoint = fields
        if kind != "_adb-tls-connect._tcp" or not name.startswith(prefix):
            continue
        try:
            endpoints.add(validate_endpoint(endpoint))
        except ValueError:
            continue
    return sorted(endpoints)


class A50ADB:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.adb = self.config["adb_path"]
        self.ssh_recovery_requested = False
        if not Path(self.adb).is_file():
            raise ConnectionError("Portable ADB executable is missing.")
        serial = self.config["device_serial"]
        if not serial or self.config["mdns_prefix"] != f"adb-{serial}-":
            raise ConnectionError("Verified device identity configuration is invalid.")

    def run(self, *args: str, timeout: float = 10) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run([self.adb, *args], capture_output=True, timeout=timeout, check=False)

    def redact(self, value: str) -> str:
        value = value.replace(self.config["device_serial"], "[REDACTED_DEVICE_ID]")
        token = self.config.get("manager_rpc_token")
        if token:
            value = value.replace(token, "[REDACTED_CAPABILITY]")
        value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[REDACTED_ADDRESS]", value)
        value = re.sub(r"\bu0_a\d+\b", "[REDACTED_APP_USER]", value)
        return re.sub(r"\buid=\d+\b", "uid=[REDACTED]", value)

    def verify(self, endpoint: str) -> bool:
        state = self.run("-s", endpoint, "get-state", timeout=4)
        if state.returncode or state.stdout.strip() != b"device":
            return False
        identity = self.run("-s", endpoint, "shell", "getprop ro.serialno", timeout=4)
        model = self.run("-s", endpoint, "shell", "getprop ro.product.model", timeout=4)
        if identity.returncode or model.returncode:
            return False
        if (
            identity.stdout.decode().strip() != self.config["device_serial"]
            or model.stdout.decode().strip() != self.config["model"]
        ):
            raise ConnectionError("Device identity mismatch; no requested command was run.")
        return True

    def recover_over_ssh(self) -> bool:
        connection = self.config_path.parent / "connection.json"
        if not connection.is_file():
            raise ConnectionError("Configured SSH recovery details are missing.")
        token = self.config.get("manager_rpc_token", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
            raise ConnectionError("Authorized management recovery token is missing or invalid.")
        request = (
            "am broadcast -a com.aircon.a50manager.RECOVER "
            "-n com.aircon.a50manager/.RecoveryReceiver --es token " + shlex.quote(token)
        )
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).with_name("a50_ssh.py")),
                "--connection",
                str(connection),
                request,
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.ssh_recovery_requested = (
            # TermuxAm returns the ordered broadcast's result code as its process exit code.
            # System am may return zero instead; both require the explicit accepted reply.
            result.returncode in (0, 1) and b"Broadcast completed: result=1" in result.stdout
        )
        return self.ssh_recovery_requested

    def connect(self, timeout: float = 30, rediscover: bool = False) -> str:
        self.ssh_recovery_requested = False
        if not rediscover and self.config.get("cached_endpoint"):
            cached = validate_endpoint(self.config["cached_endpoint"])
            try:
                if self.verify(cached):
                    return cached
            except subprocess.TimeoutExpired:
                pass
        deadline = time.monotonic() + timeout
        next_recovery = time.monotonic() + 5
        recovery_attempts = 0
        while time.monotonic() < deadline:
            try:
                discovered = self.run("mdns", "services", timeout=4)
                endpoints = discover_endpoints(
                    discovered.stdout.decode("utf-8", errors="replace"),
                    self.config["mdns_prefix"],
                )
                if len(endpoints) > 1:
                    raise ConnectionError("Multiple endpoints match; refusing an ambiguous target.")
                if endpoints:
                    endpoint = endpoints[0]
                    self.run("connect", endpoint, timeout=4)
                    if self.verify(endpoint):
                        self.config["cached_endpoint"] = endpoint
                        self.config_path.write_text(
                            json.dumps(self.config, indent=2) + "\n", encoding="utf-8"
                        )
                        return endpoint
                elif (
                    self.config.get("ssh_recovery_enabled", False)
                    and recovery_attempts < 8
                    and time.monotonic() >= next_recovery
                ):
                    recovery_attempts += 1
                    next_recovery = time.monotonic() + 30
                    self.recover_over_ssh()
            except subprocess.TimeoutExpired:
                pass
            time.sleep(1)
        raise ConnectionError(
            "Paired A50 not discovered. Wireless debugging may be off, Wi-Fi may be "
            "unavailable, or mDNS may be blocked. Ordinary SSH remains independent."
        )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(".deploy/a50/adb.json"))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--rediscover", action="store_true")
    parser.add_argument("--capture", type=Path, help="Save a private screenshot for inspection.")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error("Timeout must be between 1 and 300 seconds.")
    try:
        client = A50ADB(args.config)
        endpoint = client.connect(args.timeout, args.rediscover)
        print("ADB_READY=verified paired A50; no manual IP or port entry")
        if client.ssh_recovery_requested:
            print("SSH_MANAGEMENT_RECOVERY=authorized request accepted by phone manager")
        if args.capture:
            result = client.run("-s", endpoint, "exec-out", "screencap", "-p", timeout=20)
            if result.returncode or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ConnectionError("Screenshot capture failed.")
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            args.capture.write_bytes(result.stdout)
            print("PRIVATE_SCREENSHOT_SAVED")
            return 0
        command = args.command
        if command and command[0] == "--":
            command = command[1:]
        if command:
            result = client.run("-s", endpoint, *command, timeout=60)
            print(client.redact((result.stdout + result.stderr).decode("utf-8", errors="replace")))
            return result.returncode
        return 0
    except (ConnectionError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"ADB_UNAVAILABLE={type(error).__name__}")
        if isinstance(error, ConnectionError):
            print(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
