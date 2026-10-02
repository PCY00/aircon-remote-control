"""Linux-only installer verification using throwaway databases and fake service commands."""

import base64
import hashlib
import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path


def check_installer(install, files):
    checksum = hashlib.sha256()
    for name, data in sorted(files.items()):
        checksum.update(name.encode() + b"\0" + data + b"\0")
    payload = {
        "release": checksum.hexdigest()[:16],
        "files": {name: base64.b64encode(data).decode() for name, data in files.items()},
    }
    with tempfile.TemporaryDirectory(prefix="aircon-agent-install-test-") as temporary:
        home = Path(temporary)
        for relative, table in (
            ("sensors/sensors.sqlite3", "door_events"),
            ("automations/automations.sqlite3", "automation_events"),
        ):
            path = home / "aircon-controller/runtime" / relative
            path.parent.mkdir(parents=True)
            with sqlite3.connect(path) as conn:
                conn.execute("CREATE TABLE " + table + "(id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO " + table + " VALUES(1)")
        original = {path: path.read_bytes() for path in home.rglob("*.sqlite3")}
        commands = []

        def fake_service(command, **kwargs):
            if command[:3] == ["/usr/bin/python3", "-m", "py_compile"]:
                return subprocess.run(command, **kwargs)
            assert command[:2] == ["systemctl", "--user"]
            commands.append(command)
            return subprocess.CompletedProcess(command, 3, b"inactive", b"")

        install(payload, apply=True, home=home, runner=fake_service)
        root = home / "services/aircon-central-agent"
        ledger = json.loads((root / "deployment.json").read_text())
        assert (root / "current").is_symlink()
        assert (root / "current").resolve() == Path(ledger["release"])
        assert original == {path: path.read_bytes() for path in original}
        assert not any("enable" in command or "restart" in command for command in commands)
        assert not (home / ".config/aircon-central-agent/config.json").exists()
        print("POSIX_FIRST_APPLY_PRIVATE_LINK_CHECKSUM_AND_SOURCE_PRESERVATION=PASS")
        code = root / "current/agent.py"
        code.write_bytes(b"operator customization")
        commands.clear()
        try:
            install(payload, apply=True, home=home, runner=fake_service)
        except RuntimeError as error:
            assert "managed source changed" in str(error)
        else:
            raise AssertionError("Unmanaged edit must abort")
        assert code.read_bytes() == b"operator customization" and commands == []
        print("POSIX_REMOTE_USER_EDIT_PRESERVED_AND_NO_SERVICE_COMMAND=PASS")
    print("PI_LINUX_CHECKS=2_PASS ACTUAL_PROJECT_AND_SERVICES=UNMODIFIED")
