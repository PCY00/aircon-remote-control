"""The A50 keeps only the hub identity on disk; the token and claim code stay in the hand-off."""

import ast
import json
import os
import shutil
import sqlite3
import stat
import sys
import types
import urllib.request
from pathlib import Path

import pytest

from tests.test_central_push import setup as setup

ROOT = Path(__file__).parents[1]
RESULT = {"hub_id": "hub-1", "hub_token": "hub_" + "t" * 43, "claim_code": "CLAIM-1234",
          "claim_expires_at": 9999999999.0}


def script(relative, name):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) == name)


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config/aircon-central").mkdir(parents=True)
    (home / ".local/share/aircon-central").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(sys, "path", list(sys.path))
    if os.name == "nt":  # no POSIX mode bits here; the probe stays strict on the A50
        monkeypatch.setattr(stat, "S_IMODE", lambda mode: 0o600)
    return home


def test_provisioning_persists_only_the_hub_identity(home, monkeypatch, capsys):
    households = types.ModuleType("central_server.households")

    class Households:
        def __init__(self, db):
            self.db = db

        def provision_hub(self):
            return dict(RESULT)

    households.Households = Households
    package = types.ModuleType("central_server")
    package.households = households
    monkeypatch.setitem(sys.modules, "central_server", package)
    monkeypatch.setitem(sys.modules, "central_server.households", households)
    exec(script("scripts/pi/link_central_agent.py", "PROVISION"), {})
    assert json.loads(capsys.readouterr().out) == RESULT  # the transient hand-off keeps everything
    record = home / ".config/aircon-central/pi-central-hub.json"
    saved = json.loads(record.read_text())
    assert set(saved) == {"hub_id", "created_at"} and saved["hub_id"] == "hub-1"
    assert RESULT["hub_token"] not in record.read_text() and "CLAIM" not in record.read_text()
    if os.name != "nt":
        assert stat.S_IMODE(record.stat().st_mode) == 0o600
    with pytest.raises(SystemExit):  # an existing record is never replaced
        exec(script("scripts/pi/link_central_agent.py", "PROVISION"), {})
    assert json.loads(record.read_text()) == saved


@pytest.fixture
def paired(home, setup, monkeypatch):
    db, _, _, _, _, _, _, _, _, _, hub = setup
    with sqlite3.connect(db) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    copy = home / ".local/share/aircon-central/central.sqlite3"
    shutil.copy(db, copy)
    with sqlite3.connect(copy) as conn:
        conn.execute("PRAGMA journal_mode=DELETE")

    class Ready:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: Ready())
    return home / ".config/aircon-central/pi-central-hub.json", hub


def test_verification_reports_a_hub_id_only_record(paired, capsys):
    record, hub = paired
    record.write_text(json.dumps({"hub_id": hub["hub_id"], "created_at": 1000.0}))
    record.chmod(0o600)
    exec(script("scripts/pi/verify_central_agent.py", "PHONE_PROBE"), {})
    out = capsys.readouterr().out
    assert 'PROVISIONING_RECORD_FIELDS=["created_at", "hub_id"]' in out
    assert "PROVISIONED_HUB_ACTIVE_AND_ONE_TIME_CLAIM_CONSUMED=PASS" in out
    assert out.strip().endswith("PROVISIONING_RECORD=hub_id_only")


def test_verification_flags_a_legacy_record_that_still_holds_the_token(paired, capsys):
    record, hub = paired
    record.write_text(json.dumps(hub))  # pairings made before this change kept everything
    record.chmod(0o600)
    with pytest.raises(AssertionError, match="still holds claim_code,claim_expires_at,hub_token"):
        exec(script("scripts/pi/verify_central_agent.py", "PHONE_PROBE"), {})
    out = capsys.readouterr().out
    assert "PROVISIONED_HUB_ACTIVE_AND_ONE_TIME_CLAIM_CONSUMED=PASS" in out  # read-only part ran
    assert hub["hub_token"] not in out and hub["claim_code"] not in out
    assert "PROVISIONING_RECORD=hub_id_only" not in out


def test_first_pairing_accepts_the_current_central_server_version(monkeypatch):
    import importlib.util

    from central_server import VERSION

    monkeypatch.syspath_prepend(str(ROOT / "scripts/pi"))
    spec = importlib.util.spec_from_file_location(
        "link_under_test", ROOT / "scripts/pi/link_central_agent.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    phone = dict(version=VERSION, hubs=0, credential_exists=False)
    assert module.first_pairing_available(phone, dict(config_exists=False))
    assert not module.first_pairing_available(
        dict(phone, version="9.9.9"), dict(config_exists=False)
    )
