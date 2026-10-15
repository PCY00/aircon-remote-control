"""A saved SSH user or host must never be handed to ssh as an option."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts/android"))
import a50_adb  # noqa: E402
import a50_ssh  # noqa: E402

TOKEN = "UNIT_TEST_TOKEN_00000000000000000000000000"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connection(tmp_path, user="u0_a1", host="192.0.2.1"):
    key, known = tmp_path / "id_unit", tmp_path / "known_hosts_unit"
    key.touch()
    known.touch()
    path = tmp_path / "connection.json"
    path.write_text(
        json.dumps(
            {
                "identity_file": str(key),
                "known_hosts_file": str(known),
                "port": 8022,
                "user": user,
                "host": host,
            }
        )
    )
    return path


@pytest.mark.parametrize("user", ["-oProxyCommand=calc", "-", "-l", "u0_a1 x", ""])
def test_option_like_user_is_rejected_before_ssh_runs(tmp_path, user):
    with pytest.raises(ValueError, match="plain ssh destination"):
        a50_ssh.ssh_command(connection(tmp_path, user=user), "id")


@pytest.mark.parametrize("host", ["-oProxyCommand=calc", "-", "host name", ""])
def test_option_like_host_is_rejected_before_ssh_runs(tmp_path, host):
    with pytest.raises(ValueError, match="plain ssh destination"):
        a50_ssh.ssh_command(connection(tmp_path, host=host), "id")


@pytest.mark.parametrize(
    ("user", "host"),
    [("u0_a1", "192.0.2.1"), ("user.name-1", "phone.example.ts.net"), ("_svc", "::1")],
)
def test_plain_destinations_are_kept(tmp_path, user, host):
    command = a50_ssh.ssh_command(connection(tmp_path, user=user, host=host))
    assert command[0] == "ssh" and command[-1] == user + "@" + host


def test_recovery_with_option_like_user_sends_nothing(tmp_path, monkeypatch):
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
                "manager_rpc_token": TOKEN,
            }
        )
    )
    connection(tmp_path, user="-oProxyCommand=calc")
    monkeypatch.setattr(a50_adb.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected SSH"))
    client = a50_adb.A50ADB(config)
    assert not client.recover_over_ssh()
    assert not client.ssh_recovery_requested


@pytest.mark.parametrize("user", ["-oProxyCommand=calc", "-", ""])
def test_reader_setup_rejects_option_like_user_before_any_lookup(tmp_path, monkeypatch, user):
    module = load("reader_connections_user", "scripts/reader/setup_connections.py")
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected ssh-keygen")
    )
    key, known = tmp_path / "key", tmp_path / "known"
    key.touch()
    known.touch()
    args = argparse.Namespace(
        host="192.0.2.1", user=user, port=8022, identity_file=key, known_hosts_file=known
    )
    with pytest.raises(ValueError, match="confirmed on your own device"):
        module.known_connection(args)


def test_reader_setup_keeps_plain_user_names(tmp_path, monkeypatch):
    module = load("reader_connections_plain_user", "scripts/reader/setup_connections.py")
    key, known = tmp_path / "key", tmp_path / "known"
    key.touch()
    known.touch()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda command, **k: module.subprocess.CompletedProcess(command, 0, b"known entry", b""),
    )
    args = argparse.Namespace(
        host="192.0.2.1", user="pi.user-1", port=22, identity_file=key, known_hosts_file=known
    )
    assert module.known_connection(args)["user"] == "pi.user-1"
