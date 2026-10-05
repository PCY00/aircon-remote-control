"""Fresh-reader settings must preserve existing files and reject unconfirmed targets."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_one_existing_phone_file_prevents_all_replacements(tmp_path):
    module = load("reader_connections", "scripts/reader/setup_connections.py")
    first, existing = tmp_path / "new.json", tmp_path / "existing.json"
    existing.write_text('"keep this"')
    with pytest.raises(RuntimeError, match="already exist"):
        module.save_new([(first, {}), (existing, {})])
    assert existing.read_text() == '"keep this"'
    assert not first.exists()


def test_phone_model_mismatch_does_not_save_settings_or_print_identity(
    tmp_path, monkeypatch, capsys
):
    module = load("reader_connections_mismatch", "scripts/reader/setup_connections.py")
    key, known, adb = [tmp_path / name for name in ("key", "known", "adb.exe")]
    for path in [key, known, adb]:
        path.write_text("fixture")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup",
            "phone",
            "--host",
            "127.0.0.1",
            "--user",
            "fixture",
            "--identity-file",
            str(key),
            "--known-hosts-file",
            str(known),
            "--adb",
            str(adb),
            "--endpoint",
            "127.0.0.1:12345",
            "--root",
            str(tmp_path),
        ],
    )

    def run(command, **kwargs):
        output = (
            b"known entry"
            if command[0] == "ssh-keygen"
            else (b"PRIVATE_FIXTURE_SERIAL" if command[-1] == "ro.serialno" else b"WRONG_MODEL")
        )
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(SystemExit):
        module.main()
    assert not (tmp_path / ".deploy").exists()
    output = capsys.readouterr()
    assert "PRIVATE_FIXTURE_SERIAL" not in output.out + output.err


def test_fresh_phone_config_is_utf8_and_only_created_once(tmp_path, monkeypatch):
    module = load("reader_connections_new", "scripts/reader/setup_connections.py")
    key, known, adb = [tmp_path / name for name in ("key", "known", "adb.exe")]
    for path in [key, known, adb]:
        path.write_text("fixture")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "setup",
            "phone",
            "--host",
            "127.0.0.1",
            "--user",
            "fixture",
            "--identity-file",
            str(key),
            "--known-hosts-file",
            str(known),
            "--adb",
            str(adb),
            "--endpoint",
            "127.0.0.1:12345",
            "--root",
            str(tmp_path),
        ],
    )

    def run(command, **kwargs):
        output = (
            b"known entry"
            if command[0] == "ssh-keygen"
            else (b"FIXTURE_SERIAL" if command[-1] == "ro.serialno" else b"SM-A505N")
        )
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", run)
    module.main()
    phone = tmp_path / ".deploy/a50"
    assert (
        json.loads((phone / "adb.json").read_text(encoding="utf-8"))["mdns_prefix"]
        == "adb-FIXTURE_SERIAL-"
    )
    before = {p.name: p.read_bytes() for p in phone.iterdir()}
    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: pytest.fail("Existing settings must not connect")
    )
    with pytest.raises(SystemExit):
        module.main()
    assert before == {p.name: p.read_bytes() for p in phone.iterdir()}


@pytest.mark.parametrize("version", ["0.3.1", "0.4.0"])
def test_supported_first_pairing_still_rejects_all_existing_credentials(version):
    sys.path.insert(0, str(ROOT / "scripts/pi"))
    module = load("reader_link", "scripts/pi/link_central_agent.py")
    empty = dict(version=version, hubs=0, credential_exists=False)
    assert module.first_pairing_available(empty, dict(config_exists=False))
    assert not module.first_pairing_available(dict(empty, hubs=1), dict(config_exists=False))
    assert not module.first_pairing_available(
        dict(empty, credential_exists=True), dict(config_exists=False)
    )
    assert not module.first_pairing_available(empty, dict(config_exists=True))
    assert not module.first_pairing_available(
        dict(empty, version="UNKNOWN"), dict(config_exists=False)
    )


def test_pi_command_uses_reader_config_and_requires_known_host_file(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts/android"))
    module = load("reader_pi_session", "scripts/pi/pi_session.py")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    session = object.__new__(module.PiSession)
    with pytest.raises(RuntimeError, match="connection missing"):
        session.command()
    key, known = tmp_path / "key", tmp_path / "known"
    key.touch()
    known.touch()
    config = tmp_path / ".deploy/pi-central-agent/connection.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        json.dumps(
            dict(
                host="reader-host",
                user="reader-user",
                port=2201,
                identity_file=str(key),
                known_hosts_file=str(known),
            )
        )
    )
    command = session.command()
    assert command[-1] == "reader-user@reader-host"
    assert "StrictHostKeyChecking=yes" in command and "BatchMode=yes" in command
    assert "UserKnownHostsFile=" + str(known) in command
    known.unlink()
    with pytest.raises(RuntimeError, match="host record missing"):
        session.command()
