"""Pi captures must not name the SSH target; a crafted connection must not become an ssh option."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.fixture
def pi_session(tmp_path, monkeypatch):
    # PhoneSession reads the A50 files from the CWD and writes captures below it: all fakes here.
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".deploy/a50").mkdir(parents=True)
    (tmp_path / ".deploy/a50/connection.json").write_text(json.dumps({
        "host": "192.0.2.50", "port": 8022, "user": "u0_a999",
        "identity_file": str(tmp_path / "a50-key"),
        "known_hosts_file": str(tmp_path / "a50-known")}))
    (tmp_path / ".deploy/a50/adb.json").write_text(json.dumps({
        "adb_path": sys.executable, "device_serial": "FAKESERIAL1234", "model": "SM-A505N",
        "mdns_prefix": "adb-FAKESERIAL1234-", "cached_endpoint": "192.0.2.50:40000",
        "ssh_recovery_enabled": False}))
    spec = importlib.util.spec_from_file_location(
        "pi_session_under_test", ROOT / "scripts/pi/pi_session.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def pi_connection(tmp_path, **overrides):
    key, known = tmp_path / "pi-key", tmp_path / "pi-known"
    key.touch()
    known.touch()
    config = dict(host="pi-home", user="pi", port=22, identity_file=str(key),
                  known_hosts_file=str(known))
    config.update(overrides)
    path = tmp_path / ".deploy/pi-central-agent/connection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config))
    return config


def test_pi_target_and_tailnet_names_never_reach_the_committed_capture(pi_session, tmp_path):
    config = pi_connection(tmp_path)
    session = pi_session.PiSession("redaction")
    sample = (
        "ssh: connect to host pi-home port 22: Connection timed out\n"
        "pi@pi-home: Permission denied (publickey).\n"
        "ssh: connect to host raspberrypi.tail1234.ts.net port 22: No route to host\n"
        "other@raspberrypi.tail1234.ts.net: Permission denied (publickey).\n"
        "Warning: Identity file " + config["identity_file"] + " not accessible: No such file.\n"
        'Load key "' + config["identity_file"].replace("\\", "/") + '": bad permissions\n'
        "UserKnownHostsFile=" + config["known_hosts_file"] + "\n"
        "Received disconnect from fd7a:115c:a1e0:ab12:4843:cd96:625e:1234 port 22\n"
        "pipx api pi"
    )
    session.log(sample)
    text = session.record.read_text(encoding="utf-8")
    for private in ("pi-home", "pi@", "raspberrypi", "tail1234", "ts.net", "fd7a:115c",
                    config["identity_file"], config["known_hosts_file"], str(tmp_path)):
        assert private not in text, private
    assert "[REDACTED_PI_USER]@[REDACTED_PI_HOST]: Permission denied" in text
    assert "[REDACTED_PI_USER]@[REDACTED_TAILNET_HOST]: Permission denied" in text
    assert "Identity file [REDACTED_LOCAL_PATH] not accessible" in text
    assert 'Load key "[REDACTED_LOCAL_PATH]": bad permissions' in text
    assert "from [REDACTED_ADDRESS] port 22" in text
    assert text.endswith("pipx api [REDACTED_PI_USER]\n")  # whole words only


def test_capture_without_a_saved_pi_connection_still_hides_generic_ssh_details(pi_session):
    session = pi_session.PiSession("no-pi-file")
    session.log("someone@pi.tailnet-abcd.ts.net: Permission denied")
    assert "[REDACTED_PI_USER]@[REDACTED_TAILNET_HOST]: Permission denied" in (
        session.record.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "field,value",
    [("user", "-oProxyCommand=calc"), ("host", "-oProxyCommand=calc"), ("user", ""),
     ("user", "pi user"), ("host", ".hidden"), ("port", 70000), ("user", 7)],
)
def test_connection_that_would_become_an_ssh_option_is_refused(pi_session, tmp_path, field, value):
    pi_connection(tmp_path, **{field: value})
    session = object.__new__(pi_session.PiSession)
    with pytest.raises(RuntimeError, match="plain ssh target"):
        session.command()


def test_plain_user_host_and_port_are_passed_through(pi_session, tmp_path):
    pi_connection(tmp_path, user="pi_user.1", host="100.64.0.9", port="2201")
    command = object.__new__(pi_session.PiSession).command()
    assert command[-1] == "pi_user.1@100.64.0.9" and command[command.index("-p") + 1] == "2201"
    assert pi_session.SSH_USER.pattern == "[A-Za-z0-9_][A-Za-z0-9_.-]*"
