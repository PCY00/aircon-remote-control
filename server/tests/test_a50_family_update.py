"""Ensure APK, signer, download and credential guards still run under python -O."""

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts/android"
sys.path.insert(0, str(SCRIPTS))
import update_a50_family_app as update  # noqa: E402

# Integrity, signer and credential checks that guard installs, extraction or remote copies.
GUARDED = (
    "update_a50_family_app.py",
    "run_a50_family_smoke.py",
    "prepare_family_tools.py",
    "configure_a50_fcm.py",
    "verify_family_apk.py",
)


@pytest.mark.parametrize("name", GUARDED)
def test_guards_are_explicit_checks_not_assert_statements(name):
    tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
    assert [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)] == []


def release(tmp_path, monkeypatch, *, recorded_hash=None):
    monkeypatch.chdir(tmp_path)
    build = tmp_path / "tmp/family-app-build"
    build.mkdir(parents=True)
    apk = build / "family-release.apk"
    apk.write_bytes(b"unit test release")
    actual = hashlib.sha256(apk.read_bytes()).hexdigest()
    (build / "build.json").write_text(json.dumps({"family-release.apk": recorded_hash or actual}))
    monkeypatch.setattr(update, "A50ADB", lambda *a, **k: pytest.fail("Unexpected phone access"))
    monkeypatch.setattr(
        update, "PhoneSession", lambda *a, **k: pytest.fail("Unexpected phone access")
    )
    monkeypatch.setattr(sys, "argv", ["update_a50_family_app.py", "--apply"])


def test_changed_release_apk_stops_before_any_phone_action(tmp_path, monkeypatch):
    release(tmp_path, monkeypatch, recorded_hash="0" * 64)
    with pytest.raises(RuntimeError, match="APK changed since build"):
        update.main()


def test_other_signing_certificate_stops_before_any_phone_action(tmp_path, monkeypatch):
    release(tmp_path, monkeypatch)
    private = tmp_path / ".deploy/family-app"
    private.mkdir(parents=True)
    (private / "tools.json").write_text(json.dumps({"java_home": "jdk", "sdk": "sdk"}))
    (private / "signing.json").write_text(json.dumps({"sha256": "BB:" * 31 + "BB"}))
    monkeypatch.setattr(
        update.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 0, "Signer #1 certificate SHA-256 digest: " + "aa" * 32 + "\n", ""
        ),
    )
    with pytest.raises(RuntimeError, match="signing certificate differs"):
        update.main()


def test_debuggable_release_apk_is_refused_before_any_phone_action(tmp_path, monkeypatch):
    release(tmp_path, monkeypatch)
    private = tmp_path / ".deploy/family-app"
    private.mkdir(parents=True)
    (private / "tools.json").write_text(json.dumps({"java_home": "jdk", "sdk": "sdk"}))
    (private / "signing.json").write_text(json.dumps({"sha256": "AA:" * 31 + "AA"}))

    def run(command, **kwargs):
        if "apksigner.jar" in command[2]:
            output = "Signer #1 certificate SHA-256 digest: " + "aa" * 32 + "\n"
        else:
            output = "package: name='com.aircon.family'\napplication-debuggable\n"
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(update.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="debuggable"):
        update.main()


def test_changed_release_apk_is_rejected_under_python_optimize(tmp_path):
    build = tmp_path / "tmp/family-app-build"
    build.mkdir(parents=True)
    (build / "family-release.apk").write_bytes(b"unit test release")
    (build / "build.json").write_text(json.dumps({"family-release.apk": "0" * 64}))
    result = subprocess.run(
        [sys.executable, "-O", str(SCRIPTS / "update_a50_family_app.py")],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "APK changed since build" in result.stderr
