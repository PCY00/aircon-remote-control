"""Rediscover the paired A50 over mDNS and verify its identity before any command."""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from a50_ssh import ssh_command


class ConnectionError(RuntimeError):
    """The configured phone could not be safely selected."""


# Public captures must not carry the PC account, LAN/Tailscale/tunnel identifiers or pairing codes.
MAC_ADDRESS = re.compile(r"(?<![\w:.-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![\w:.-])")
IPV6_ADDRESS = re.compile(
    r"(?<![\w:.])(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){1,7}:(?:[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6})?"
    r"|::[0-9A-Fa-f]{1,4}(?::[0-9A-Fa-f]{1,4}){0,6}"
    r")(?:%\w+)?(?:/\d{1,3})?(?![\w:.])"
)
TAILNET_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9.-]*\.ts\.net\b")
TUNNEL_HOST = re.compile(r"\b[A-Za-z0-9][A-Za-z0-9.-]*\.trycloudflare\.com\b")
# Six digits only in a pairing/code context; byte counts and timestamps keep their digits.
PAIRING_CODE = re.compile(r"(?i)\b(pair(?:ing)?|code)\b([^\d\n]{0,32}?)\b(\d{6})\b")


def local_user_names() -> set[str]:
    """Account names of this PC that may appear in paths, prompts and pytest temp directories."""
    names = {os.environ.get("USERNAME"), os.environ.get("USER")}
    try:
        names.add(getpass.getuser())
    except (OSError, KeyError, ImportError):
        pass
    return {name for name in names if name and len(name) >= 3}


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
        value = re.sub(r"pytest-of-[^\\/\s]+", "pytest-of-[REDACTED_USER]", value)
        for name in sorted(local_user_names(), key=len, reverse=True):
            value = re.sub(r"(?<!\w)" + re.escape(name) + r"(?!\w)", "[REDACTED_USER]", value)
        value = MAC_ADDRESS.sub("[REDACTED_MAC]", value)
        value = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b", "[REDACTED_ADDRESS]", value)
        value = IPV6_ADDRESS.sub("[REDACTED_ADDRESS]", value)
        value = TAILNET_HOST.sub("[REDACTED_TAILNET_HOST]", value)
        value = TUNNEL_HOST.sub("[REDACTED_TUNNEL_HOST]", value)
        value = PAIRING_CODE.sub(r"\1\2[REDACTED_CODE]", value)
        value = re.sub(r"\bu0_a\d+\b", "[REDACTED_APP_USER]", value)
        return re.sub(r"\buid=\d+\b", "uid=[REDACTED]", value)

    def dump_ui(
        self, endpoint: str, name: str, timeout: float = 30
    ) -> subprocess.CompletedProcess[bytes]:
        """Read the current UI hierarchy; the temporary dump is removed in the same command."""
        if not re.fullmatch(r"[a-z0-9-]{1,40}", name):
            raise ValueError("Invalid UI dump name")
        path = "/data/local/tmp/" + name + ".xml"
        script = (
            "uiautomator dump " + path + " >/dev/null && cat " + path
            + "; s=$?; rm -f " + path + "; exit $s"
        )
        return self.run("-s", endpoint, "exec-out", script, timeout=timeout)

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
        try:
            command = ssh_command(connection, request)
        except (OSError, ValueError, KeyError, TypeError):
            # Incomplete local SSH details: no request was sent; keep polling ADB as before.
            self.ssh_recovery_requested = False
            return False
        try:
            # Run ssh as the direct child so the timeout kill reaches it and releases the pipes.
            result = subprocess.run(command, capture_output=True, timeout=20, check=False)
        except OSError:
            # No usable ssh client: a failed attempt, so connect() keeps polling ADB.
            self.ssh_recovery_requested = False
            return False
        self.ssh_recovery_requested = (
            # TermuxAm returns the ordered broadcast's result code as its process exit code.
            # System am may return zero instead; both require the explicit accepted reply.
            result.returncode in (0, 1) and b"Broadcast completed: result=1" in result.stdout
        )
        return self.ssh_recovery_requested

    def persist_endpoint(self, endpoint: str) -> None:
        # Update only the cached endpoint; in-memory overrides must never reach the file.
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        saved["cached_endpoint"] = endpoint
        self.config_path.write_text(json.dumps(saved, indent=2) + "\n", encoding="utf-8")

    def connect(
        self,
        timeout: float = 30,
        rediscover: bool = False,
        allow_ssh_recovery: bool | None = None,
    ) -> str:
        self.ssh_recovery_requested = False
        recovery_enabled = (
            self.config.get("ssh_recovery_enabled", False)
            if allow_ssh_recovery is None
            else allow_ssh_recovery
        )
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
                        self.persist_endpoint(endpoint)
                        return endpoint
                elif (
                    recovery_enabled
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
