"""A supervised, explicitly enabled Quick Tunnel; endpoint and raw logs stay private."""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

URL = re.compile(r"https://([a-z0-9]+(?:-[a-z0-9]+)*)\.trycloudflare\.com\b")
STATE = Path.home() / ".local/state/aircon-public-tunnel"
SERVICE = (
    Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    / "var/service/aircon-public-tunnel"
)


def quick_url(line: str) -> str | None:
    for match in URL.finditer(line):
        if match.group(1) not in {"api", "www"}:
            return match.group(0)
    return None


def save_endpoint(state: Path, *, status: str, url: str | None, pid: int,
                  mode: str = "quick-test") -> None:
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / "endpoint.json"
    temporary = path.with_suffix(".new")
    temporary.write_text(
        json.dumps(
            {
                "status": status,
                "url": url,
                "supervisor_pid": pid,
                "updated_at": time.time(),
                "mode": mode,
            }
        ),
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)


def record_failure(state: Path, service: Path, *, status: int, sig: int, now: float) -> int:
    if status == 0 or sig in (2, 15):
        return 0
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state / "restart-state.json"
    try:
        failures = json.loads(path.read_text())["failures"] if path.exists() else []
        if not isinstance(failures, list) or not all(type(x) in (int, float) for x in failures):
            raise ValueError("Invalid failure history")
    except (ValueError, KeyError, OSError):
        failures = [now] * 5
    failures = [x for x in failures if now - x < 300] + [now]
    path.write_text(json.dumps({"failures": failures[-5:]}), encoding="utf-8")
    if len(failures) >= 5:
        (service / "down").touch(mode=0o600)
        try:
            fd = os.open(service / "supervise/control", os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, b"d")
            finally:
                os.close(fd)
        except (OSError, AttributeError):
            pass
        print("TUNNEL_RESTART_BLOCKED limit=5 window_seconds=300", flush=True)
    else:
        print(f"TUNNEL_ABNORMAL_EXIT attempt={len(failures)}/5", flush=True)
    return min(len(failures), 5)


def fixed_command(config_path: Path) -> tuple[list[str], str]:
    """Read one private, remotely managed tunnel credential without putting it in argv."""
    value = json.loads(config_path.read_text(encoding="utf-8"))
    hostname = value.get("hostname", "")
    if set(value) != {"hostname", "token_file"} or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
        r"[a-z]{2,63}", hostname
    ):
        raise ValueError("Invalid fixed tunnel configuration")
    token_file = Path(value["token_file"])
    if not token_file.is_absolute() or token_file.is_symlink() or not token_file.is_file():
        raise ValueError("Private tunnel token file required")
    if config_path.stat().st_mode & 0o077 or token_file.stat().st_mode & 0o077:
        raise ValueError("Tunnel configuration and credential must be owner-only")
    if not token_file.read_text(encoding="ascii").strip():
        raise ValueError("Empty tunnel credential")
    return (["cloudflared", "tunnel", "--no-autoupdate", "--protocol", "http2",
             "--metrics", "127.0.0.1:19344", "run", "--token-file", str(token_file)],
            "https://" + hostname)


def run(*, state: Path | None = None, config_path: Path | None = None) -> int:
    os.umask(0o077)
    state = state if state is not None else STATE
    mode = "fixed" if config_path is not None else "quick-test"

    def save(status, url=None):
        save_endpoint(state, status=status, url=url, pid=os.getpid(), mode=mode)

    save("starting")
    try:
        command, configured_endpoint = fixed_command(config_path) if config_path else (
            ["cloudflared", "tunnel", "--no-autoupdate", "--protocol", "http2",
             "--metrics", "127.0.0.1:19343", "--url", "http://127.0.0.1:8001"], None
        )
    except (OSError, ValueError, TypeError):
        save("failed")
        print("TUNNEL_PRIVATE_CONFIG_INVALID", flush=True)
        return 1
    logger = logging.getLogger("tunnel")
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        state / "cloudflared.log", maxBytes=1048576, backupCount=3, encoding="utf-8"
    )
    logger.addHandler(handler)
    stopping = False
    child = None

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            child.terminate()
            signal.alarm(10)

    def force_stop(signum, frame):
        if child is not None and child.poll() is None:
            child.kill()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGALRM, force_stop)
    # Wait for the separately managed central API before opening the requested route.
    for _ in range(30):
        if stopping:
            save("stopped")
            return 0
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8001/health/ready", timeout=2
            ) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        print("TUNNEL_ORIGIN_NOT_READY", flush=True)
        save("failed")
        return 1
    # A stop that arrived during the final probe found no child to terminate.
    if stopping:
        save("stopped")
        return 0
    child = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if stopping:  # Signal arrived while spawning, before the handler could see the child.
        child.terminate()
        signal.alarm(10)
    print(f"TUNNEL_START mode={mode} origin=loopback protocol=http2", flush=True)
    endpoint = configured_endpoint
    try:
        for line in child.stdout:
            logger.info("%s", line.rstrip()[:4096])
            candidate = quick_url(line) if config_path is None else None
            if candidate:
                endpoint = candidate
                save("connecting", endpoint)
            if "Registered tunnel connection" in line and endpoint:
                save("connected", endpoint)
                print("TUNNEL_CONNECTED endpoint_saved_privately=TRUE", flush=True)
        code = child.wait(timeout=15)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        signal.alarm(0)
        save("stopped" if stopping else "failed")
    # Even an unexpected clean child exit must not restart indefinitely.
    return 0 if stopping else (code or 1)


if __name__ == "__main__":
    os.umask(0o077)
    if len(sys.argv) > 1 and sys.argv[1] == "finish":
        count = record_failure(
            STATE, SERVICE, status=int(sys.argv[2]), sig=int(sys.argv[3]), now=time.time()
        )
        if 0 < count < 5:
            time.sleep(min(5 * count, 20))
    else:
        raise SystemExit(run())
