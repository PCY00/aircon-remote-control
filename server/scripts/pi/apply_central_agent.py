"""Remote manifest installer; preserve the existing Pi application, data and private config."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

FILES = {"agent.py", "aircon-central-agent.service"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install(payload, *, apply=False, home=None, runner=subprocess.run):
    home = Path.home() if home is None else Path(home)
    root = home / "services/aircon-central-agent"
    unit = home / ".config/systemd/user/aircon-central-agent.service"
    ledger = root / "deployment.json"
    current = root / "current"
    state = home / ".local/state/aircon-central-agent"
    config = home / ".config/aircon-central-agent/config.json"
    if set(payload["files"]) != FILES or not re.fullmatch(r"[0-9a-f]{16}", payload["release"]):
        raise ValueError("Unexpected managed manifest")
    contents = {
        name: base64.b64decode(value, validate=True) for name, value in payload["files"].items()
    }
    checksum = hashlib.sha256()
    for name, data in sorted(contents.items()):
        checksum.update(name.encode() + b"\0" + data + b"\0")
    if checksum.hexdigest()[:16] != payload["release"]:
        raise ValueError("Manifest checksum mismatch")
    previous = json.loads(ledger.read_text()) if ledger.is_file() else None
    if previous:
        release = Path(previous["release"])
        if release.parent != root / "releases" or current.resolve() != release:
            raise RuntimeError("Unexpected current release; preserve and inspect")
        expected_paths = {str(release / name) for name in FILES} | {str(unit)}
        if set(previous["managed"]) != expected_paths:
            raise RuntimeError("Unexpected ledger; preserve and inspect")
        for name, expected in previous["managed"].items():
            if not Path(name).is_file() or digest(Path(name)) != expected:
                raise RuntimeError("Remote managed source changed; preserve and inspect")
    elif any(path.exists() or path.is_symlink() for path in (root, unit, config, state)):
        raise RuntimeError("Untracked agent files exist; preserve and inspect")
    # These are the user-confirmed existing project databases. Never create or write them.
    source = home / "aircon-controller/runtime"
    for relative, table in (
        ("sensors/sensors.sqlite3", "door_events"),
        ("automations/automations.sqlite3", "automation_events"),
    ):
        path = source / relative
        if not path.is_file():
            raise RuntimeError("Verified source database unavailable")
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        print("READONLY_SOURCE=" + table + " ROWS=" + str(count), flush=True)
    active = runner(
        ["systemctl", "--user", "is-active", "aircon-central-agent"],
        capture_output=True,
        check=False,
    )
    is_active = active.stdout.strip() == b"active"
    if is_active and not previous:
        raise RuntimeError("Untracked service active; preserve and inspect")
    if is_active and not config.is_file():
        raise RuntimeError("Active service lacks private configuration")
    print("MANIFEST_FILES=2 RELEASE=" + payload["release"], flush=True)
    print("EXISTING_PI_APP_FILES_AND_DATABASES=NO_WRITE NO_APP_RESTART=TRUE", flush=True)
    print("AGENT_SERVICE=" + ("active" if is_active else "inactive"), flush=True)
    if not apply:
        print("PREVIEW_ONLY=NO_REMOTE_MUTATION", flush=True)
        return
    os.umask(0o077)
    release = root / "releases" / payload["release"]
    release.mkdir(parents=True, mode=0o700, exist_ok=True)
    state.mkdir(parents=True, mode=0o700, exist_ok=True)
    for name, content in contents.items():
        path = release / name
        if path.exists():
            if path.read_bytes() != content:
                raise RuntimeError("Immutable release differs; preserve and inspect")
        else:
            with path.open("xb") as output:
                output.write(content)
        path.chmod(0o600)
    runner(["/usr/bin/python3", "-m", "py_compile", str(release / "agent.py")], check=True)
    unit.parent.mkdir(parents=True, exist_ok=True)
    temporary = unit.with_suffix(".new")
    with temporary.open("xb") as output:
        output.write(contents["aircon-central-agent.service"])
    temporary.chmod(0o600)
    temporary.replace(unit)
    staged = root / "current.new"
    if staged.exists() or staged.is_symlink():
        raise RuntimeError("Unexpected staging link; preserve and inspect")
    staged.symlink_to(release, target_is_directory=True)
    staged.replace(current)
    managed = {str(release / name): digest(release / name) for name in FILES}
    managed[str(unit)] = digest(unit)
    temporary = ledger.with_suffix(".new")
    with temporary.open("x", encoding="utf-8") as output:
        json.dump({"release": str(release), "managed": managed}, output)
    temporary.replace(ledger)
    runner(["systemctl", "--user", "daemon-reload"], check=True)
    if is_active:
        runner(["systemctl", "--user", "restart", "aircon-central-agent"], check=True)
    else:
        print("FIRST_INSTALL_NOT_STARTED=TRUE PRIVATE_PAIRING_REQUIRED=TRUE", flush=True)
    for name, expected in managed.items():
        if digest(Path(name)) != expected:
            raise RuntimeError("Deployed checksum mismatch")
    print("AGENT_CODE_AND_UNIT_SHA256_MATCH=PASS", flush=True)
