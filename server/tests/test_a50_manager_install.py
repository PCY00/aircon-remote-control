"""Ensure a management APK update never rewrites the saved SSH recovery preference."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts/android"))
import a50_adb  # noqa: E402
import install_a50_manager as installer  # noqa: E402

TOKEN = "UNIT_TEST_TOKEN_00000000000000000000000000"
STALE, CURRENT = "192.0.2.1:40000", "192.0.2.1:41111"


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    build = tmp_path / "build"
    build.mkdir()
    apk = build / "a50-manager.apk"
    apk.write_bytes(b"unit test apk")
    (build / "build.json").write_text(
        json.dumps({"apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest()})
    )
    adb = tmp_path / "adb.exe"
    adb.touch()
    config = tmp_path / "adb.json"
    saved = {
        "adb_path": str(adb),
        "device_serial": "EXPECTED",
        "model": "SM-A505N",
        "mdns_prefix": "adb-EXPECTED-",
        "cached_endpoint": STALE,
        "ssh_recovery_enabled": True,
        "manager_rpc_token": TOKEN,
    }
    config.write_text(json.dumps(saved))
    monkeypatch.setattr(
        sys, "argv",
        ["install_a50_manager.py", "--apply", "--config", str(config), "--build", str(build)],
    )
    monkeypatch.setattr(
        a50_adb.A50ADB, "recover_over_ssh", lambda self: pytest.fail("Unexpected recovery RPC")
    )
    return config, saved


def test_rediscovered_update_target_keeps_saved_recovery_preference(workspace, monkeypatch):
    config, saved = workspace
    calls = []

    def run(self, *args, timeout=10):
        calls.append(args)
        reply, code = b"", 0
        if args == ("mdns", "services"):
            reply = b"adb-EXPECTED-a _adb-tls-connect._tcp " + CURRENT.encode() + b"\n"
        elif args == ("-s", STALE, "get-state"):
            reply = b"offline\n"
        elif args == ("-s", CURRENT, "get-state"):
            reply = b"device\n"
        elif args == ("-s", CURRENT, "shell", "getprop ro.serialno"):
            reply = b"EXPECTED\n"
        elif args == ("-s", CURRENT, "shell", "getprop ro.product.model"):
            reply = b"SM-A505N\n"
        elif args == ("-s", CURRENT, "shell", "cmd wifi status"):
            code = 1
        return subprocess.CompletedProcess(args, code, reply, b"")

    monkeypatch.setattr(a50_adb.A50ADB, "run", run)
    with pytest.raises(RuntimeError, match="Current Wi-Fi could not be measured"):
        installer.main()
    assert ("-s", CURRENT, "shell", "cmd wifi status") in calls
    assert json.loads(config.read_text()) == dict(saved, cached_endpoint=CURRENT)


def test_update_target_selection_never_sends_recovery_rpc(workspace, monkeypatch):
    config, saved = workspace
    elapsed = [0]
    monkeypatch.setattr(a50_adb.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        a50_adb.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
    )
    monkeypatch.setattr(
        a50_adb.A50ADB,
        "run",
        lambda self, *args, timeout=10: subprocess.CompletedProcess(args, 0, b"", b""),
    )
    with pytest.raises(a50_adb.ConnectionError, match="not discovered"):
        installer.main()
    assert json.loads(config.read_text()) == saved
