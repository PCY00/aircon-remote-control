"""Ensure automatic management never selects an unrelated or ambiguous device."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "a50_adb", Path(__file__).parents[1] / "scripts/android/a50_adb.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_discovery_selects_only_paired_device_tls_service():
    output = (
        "adb-EXPECTED-new _adb-tls-connect._tcp 192.0.2.1:43210\n"
        "adb-OTHER-new _adb-tls-connect._tcp 192.0.2.2:43211\n"
        "adb-EXPECTED-pair _adb-tls-pairing._tcp 192.0.2.1:43212\n"
        "adb-EXPECTED-old _adb._tcp 192.0.2.1:5555\n"
        "adb-EXPECTED-bad _adb-tls-connect._tcp 192.0.2.1:70000\n"
    )
    assert module.discover_endpoints(output, "adb-EXPECTED-") == ["192.0.2.1:43210"]


def client(tmp_path):
    binary = tmp_path / "adb.exe"
    binary.touch()
    config = tmp_path / "adb.json"
    config.write_text(
        json.dumps(
            {
                "adb_path": str(binary),
                "device_serial": "EXPECTED",
                "model": "SM-A505N",
                "mdns_prefix": "adb-EXPECTED-",
            }
        )
    )
    return module.A50ADB(config)


def test_connected_wrong_device_identity_is_rejected(tmp_path, monkeypatch):
    target = client(tmp_path)
    answers = iter([b"device\n", b"OTHER\n", b"SM-A505N\n"])
    monkeypatch.setattr(
        target, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, next(answers), b"")
    )
    with pytest.raises(module.ConnectionError, match="identity mismatch"):
        target.verify("192.0.2.1:43210")


def test_multiple_endpoints_fail_before_connect_or_command(tmp_path, monkeypatch):
    target = client(tmp_path)
    output = (
        b"adb-EXPECTED-a _adb-tls-connect._tcp 192.0.2.1:43210\n"
        b"adb-EXPECTED-b _adb-tls-connect._tcp 192.0.2.2:43211\n"
    )
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, output, b"")

    monkeypatch.setattr(target, "run", run)
    with pytest.raises(module.ConnectionError, match="Multiple endpoints"):
        target.connect(timeout=1, rediscover=True)
    assert calls == [("mdns", "services")]


@pytest.mark.parametrize("process_exit", [0, 1])
def test_ssh_recovery_uses_verified_local_connection_without_requested_command(
    tmp_path, monkeypatch, process_exit
):
    target = client(tmp_path)
    connection = tmp_path / "connection.json"
    connection.write_text("{}")
    target.config["manager_rpc_token"] = "UNIT_TEST_TOKEN_00000000000000000000000000"
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, process_exit, b"Broadcast completed: result=1", b""
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    assert target.recover_over_ssh()
    assert calls[0][-3:] == [
        "--connection",
        str(connection),
        "am broadcast -a com.aircon.a50manager.RECOVER "
        "-n com.aircon.a50manager/.RecoveryReceiver "
        "--es token UNIT_TEST_TOKEN_00000000000000000000000000",
    ]
    assert Path(calls[0][1]).name == "a50_ssh.py"


def test_ssh_recovery_refuses_missing_connection_config(tmp_path, monkeypatch):
    target = client(tmp_path)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected SSH"))
    with pytest.raises(module.ConnectionError, match="SSH recovery details are missing"):
        target.recover_over_ssh()


def test_ssh_recovery_refuses_missing_capability_before_remote_action(tmp_path, monkeypatch):
    target = client(tmp_path)
    (tmp_path / "connection.json").write_text("{}")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected SSH"))
    with pytest.raises(module.ConnectionError, match="token is missing or invalid"):
        target.recover_over_ssh()


@pytest.mark.parametrize(
    ("process_exit", "reply"),
    [(0, b"Broadcast completed: result=0"), (1, b""), (2, b"Broadcast completed: result=1")],
)
def test_recovery_requires_accepted_reply_and_expected_process_exit(
    tmp_path, monkeypatch, process_exit, reply
):
    target = client(tmp_path)
    (tmp_path / "connection.json").write_text("{}")
    target.config["manager_rpc_token"] = "UNIT_TEST_TOKEN_00000000000000000000000000"
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, process_exit, reply, b""),
    )
    assert not target.recover_over_ssh()


def test_accepted_rpc_is_retried_until_adb_is_actually_available(tmp_path, monkeypatch):
    target = client(tmp_path)
    target.config["ssh_recovery_enabled"] = True
    elapsed = [0]
    requests = []
    monkeypatch.setattr(module.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
    )

    def recover():
        requests.append(elapsed[0])
        target.ssh_recovery_requested = True
        return True

    def run(*args, **kwargs):
        reply = b""
        if args == ("mdns", "services") and len(requests) >= 2:
            reply = b"adb-EXPECTED-a _adb-tls-connect._tcp 192.0.2.1:43210\n"
        return subprocess.CompletedProcess(args, 0, reply, b"")

    monkeypatch.setattr(target, "recover_over_ssh", recover)
    monkeypatch.setattr(target, "run", run)
    monkeypatch.setattr(target, "verify", lambda endpoint: endpoint == "192.0.2.1:43210")
    assert target.connect(timeout=60, rediscover=True) == "192.0.2.1:43210"
    assert requests == [5, 35]
