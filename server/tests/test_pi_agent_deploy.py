"""Default deployment preview and drift protection must preserve all existing files."""

import base64
import hashlib
import importlib.util
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "pi_agent_installer", ROOT / "scripts/pi/apply_central_agent.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def target(tmp_path):
    for relative, table in (
        ("sensors/sensors.sqlite3", "door_events"),
        ("automations/automations.sqlite3", "automation_events"),
    ):
        path = tmp_path / "aircon-controller/runtime" / relative
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE " + table + "(id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO " + table + " VALUES(1)")
    sources = {
        name: (ROOT / "services/pi-central-agent" / name).read_bytes() for name in installer.FILES
    }
    checksum = hashlib.sha256()
    for name, data in sorted(sources.items()):
        checksum.update(name.encode() + b"\0" + data + b"\0")
    payload = {
        "release": checksum.hexdigest()[:16],
        "files": {name: base64.b64encode(data).decode() for name, data in sources.items()},
    }
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 3, b"inactive", b"")

    return tmp_path, payload, calls, run


def test_default_preview_only_reads_and_never_reloads_or_creates_files(target):
    home, payload, calls, run = target
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    installer.install(payload, home=home, runner=run)
    assert before == {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    assert calls == [["systemctl", "--user", "is-active", "aircon-central-agent"]]


@pytest.mark.skipif(os.name == "nt", reason="Linux symlink check runs on Pi temporary fixture")
def test_first_apply_does_not_start_service_or_modify_source_history(target):
    home, payload, calls, run = target
    before = {p: p.read_bytes() for p in (home / "aircon-controller").rglob("*.sqlite3")}
    installer.install(payload, home=home, runner=run, apply=True)
    assert before == {p: p.read_bytes() for p in before}
    assert (home / "services/aircon-central-agent/current").is_symlink()
    assert ["systemctl", "--user", "daemon-reload"] in calls
    assert not any("enable" in c or "restart" in c for c in calls)
    assert not (home / ".config/aircon-central-agent/config.json").exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux symlink check runs on Pi temporary fixture")
def test_remote_user_edit_aborts_before_mutation(target):
    home, payload, calls, run = target
    installer.install(payload, home=home, runner=run, apply=True)
    path = home / "services/aircon-central-agent/current/agent.py"
    path.write_bytes(b"user customization")
    calls.clear()
    with pytest.raises(RuntimeError, match="managed source changed"):
        installer.install(payload, home=home, runner=run, apply=True)
    assert path.read_bytes() == b"user customization"
    assert calls == []


def test_untracked_private_config_is_never_overwritten(target):
    home, payload, calls, run = target
    path = home / ".config/aircon-central-agent/config.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"private operator file")
    with pytest.raises(RuntimeError, match="Untracked agent"):
        installer.install(payload, home=home, runner=run, apply=True)
    assert path.read_bytes() == b"private operator file"
    assert calls == []


def test_manifest_hash_tampering_is_rejected_before_contacting_service(target):
    home, payload, calls, run = target
    payload["files"]["agent.py"] = base64.b64encode(b"unexpected change").decode()
    with pytest.raises(ValueError, match="checksum mismatch"):
        installer.install(payload, home=home, runner=run, apply=True)
    assert calls == []
