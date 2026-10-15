"""configure_control.py must not enable control on an agent release that would reject it."""

import ast
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
PROBE = next(
    ast.literal_eval(node.value)
    for node in ast.parse((ROOT / "scripts/pi/configure_control.py").read_text(encoding="utf-8")).body
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == "PROBE"
)
# The pre-control release accepted only endpoint, hub_token and source_data_dir.
OLD_AGENT = 'def load_config(path):\n    raise ValueError("Unknown private configuration")\n'


class Reply:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, *args):
        return json.dumps(self.body).encode()


class Opener:
    def open(self, url, timeout):
        if isinstance(url, urllib.request.Request):
            assert url.get_header('User-agent') == 'FamilySmartHome-ConnectivityCheck/0.1'
            url = url.full_url
        if url.endswith("/api/v1/devices"):
            binding = {"type": "h2_ir"}
            return Reply({"items": [{"profile_id": "air_conditioner/Carrier/CS-A061GS",
                                     "zigbee_binding": binding}]})
        return Reply({"database": "ok"})


@pytest.fixture
def pi(tmp_path, monkeypatch):
    home = tmp_path / "home"
    path = home / ".config/aircon-central-agent/config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"endpoint": "https://old.example.test", "hub_token": "hub_" + "x" * 43,
                                "source_data_dir": str(tmp_path)}))
    path.chmod(0o600)
    current = home / "services/aircon-central-agent/current"
    current.mkdir(parents=True)
    proc = tmp_path / "proc"
    proc.mkdir()
    (proc / "cmdline").write_bytes(b"\0".join([b"python3", b"--host", b"127.0.0.1", b"--port", b"8001", b""]))
    calls, unit = [], {"states": ["active"], "failing_restarts": 0}

    def run(command, **kwargs):
        calls.append(command[2])
        if command[2] == "restart" and unit["failing_restarts"]:
            unit["failing_restarts"] -= 1
            raise subprocess.CalledProcessError(1, command)
        output = str(proc) if command[2] == "show" else ""
        if command[2] == "is-active":
            output = unit["states"].pop(0) if len(unit["states"]) > 1 else unit["states"][0]
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: Opener())
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(sys, "path", list(sys.path))
    if os.name == "nt":
        # Windows has no POSIX group/other bits; the agent's privacy check stays strict on the Pi.
        monkeypatch.setattr(stat, "S_IRWXG", 0)
        monkeypatch.setattr(stat, "S_IRWXO", 0)
    sys.modules.pop("agent", None)
    yield current, path, calls, unit
    sys.modules.pop("agent", None)


def probe(apply, expected=None):
    exec(PROBE, {"target": "https://new.example.test", "expected": expected, "apply": apply})


def test_apply_refuses_an_agent_release_without_control_support(pi, capsys):
    current, path, calls, _ = pi
    (current / "agent.py").write_text(OLD_AGENT)
    raw = path.read_bytes()
    probe(False)
    assert json.loads(capsys.readouterr().out)["agent_control_supported"] is False
    with pytest.raises(AssertionError, match="lacks control support"):
        probe(True, hashlib.sha256(raw).hexdigest())
    assert path.read_bytes() == raw
    assert sorted(p.name for p in path.parent.iterdir()) == ["config.json"]
    assert "restart" not in calls


def test_apply_validates_config_with_deployed_agent_and_checks_it_stays_active(pi, capsys):
    current, path, calls, _ = pi
    shutil.copy(ROOT / "services/pi-central-agent/agent.py", current / "agent.py")
    probe(True, hashlib.sha256(path.read_bytes()).hexdigest())
    assert json.loads(capsys.readouterr().out)["agent_control_supported"] is True
    config = json.loads(path.read_text())
    assert config["control_origin"] == "http://127.0.0.1:8001"
    assert config["endpoint"] == "https://new.example.test"
    assert calls[-7:] == ["restart"] + ["is-active"] * 6


@pytest.mark.parametrize("states,failing_restarts", [
    (["activating"], 0),
    # Starts, then exits on a later loop and waits for its automatic restart.
    (["active", "active", "active", "activating"], 0),
    (["active"], 1),
])
def test_agent_that_does_not_stay_active_gets_previous_configuration_back(pi, states, failing_restarts):
    current, path, calls, unit = pi
    shutil.copy(ROOT / "services/pi-central-agent/agent.py", current / "agent.py")
    unit.update(states=states, failing_restarts=failing_restarts)
    raw = path.read_bytes()
    with pytest.raises(AssertionError, match="previous configuration restored"):
        probe(True, hashlib.sha256(raw).hexdigest())
    assert path.read_bytes() == raw
    assert calls.count("restart") == 2
    assert sorted(p.name for p in path.parent.iterdir() if not p.name.startswith("config.before-control-")) == [
        "config.json"]
