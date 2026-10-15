"""Family APK tooling: release build by default, no debuggable release, no UI dump left behind."""

import hashlib
import json
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "scripts/android"
sys.path.insert(0, str(SCRIPTS))
import a50_adb  # noqa: E402
import install_test_family_app as install  # noqa: E402
import verify_family_apk as verify  # noqa: E402

ENDPOINT = "192.0.2.1:43210"
LOGIN_UI = (
    '<hierarchy><node package="com.aircon.family" text="우리 집을 함께"/>'
    '<node package="com.aircon.family" text="Google로 계속하기"/>'
    '<node package="com.aircon.family" text="PRIVATE-ACCOUNT-TEXT"/></hierarchy>'
).encode("utf-8")
PNG = b"\x89PNG\r\n\x1a\nunit"
FIREBASE = {
    "project_info": {"project_id": "unit-project", "project_number": "123456789012"},
    "client": [
        {
            "client_info": {
                "android_client_info": {"package_name": "com.aircon.family"},
                "mobilesdk_app_id": "1:123456789012:android:unit",
            },
            "oauth_client": [{"client_type": 3, "client_id": "unit.apps.googleusercontent.com"}],
            "api_key": [{"current_key": "unit-api-key"}],
        }
    ],
}


def phone_files(root):
    """Fake private phone settings so PhoneSession and A50ADB construct without a device."""
    private = root / ".deploy/a50"
    private.mkdir(parents=True)
    binary = root / "adb.exe"
    binary.touch()
    (private / "adb.json").write_text(
        json.dumps(
            {
                "adb_path": str(binary),
                "device_serial": "EXPECTED",
                "model": "SM-A505N",
                "mdns_prefix": "adb-EXPECTED-",
            }
        )
    )
    (private / "connection.json").write_text(
        json.dumps(
            {
                "identity_file": str(root / "key"),
                "known_hosts_file": str(root / "known"),
                "port": 8022,
                "user": "u0_a1",
                "host": "192.0.2.1",
            }
        )
    )


def build(root, names):
    folder = root / "tmp/family-app-build"
    folder.mkdir(parents=True)
    hashes = {}
    for name in names:
        (folder / name).write_bytes(("unit " + name).encode())
        hashes[name] = hashlib.sha256((folder / name).read_bytes()).hexdigest()
    (folder / "build.json").write_text(json.dumps(hashes))
    return folder


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    phone_files(tmp_path)
    build(tmp_path, ["family-debug.apk", "family-release.apk"])
    calls = []

    def run(self, *args, timeout=10):
        calls.append(args)
        reply = b""
        if args[2:4] == ("install", "-r"):
            reply = b"Success\n"
        elif args[2] == "exec-out" and "uiautomator dump" in args[3]:
            reply = LOGIN_UI
        elif args[2:5] == ("exec-out", "screencap", "-p"):
            reply = PNG
        return subprocess.CompletedProcess(args, 0, reply, b"")

    monkeypatch.setattr(a50_adb.A50ADB, "run", run)
    monkeypatch.setattr(a50_adb.A50ADB, "connect", lambda self, timeout=30, **kwargs: ENDPOINT)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    return calls


def installed(calls):
    return [Path(args[4]).name for args in calls if args[2:4] == ("install", "-r")]


def test_production_only_installs_the_release_build_by_default(workspace, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["install_test_family_app.py", "--production-only", "--apply"])
    install.main()
    assert installed(workspace) == ["family-release.apk"]
    dumps = [args for args in workspace if "uiautomator" in " ".join(args)]
    assert len(dumps) == 1 and dumps[0][2] == "exec-out"
    assert "rm -f /data/local/tmp/family-production-ui.xml" in dumps[0][3]
    assert not any(args[2:5] == ("shell", "uiautomator", "dump") for args in workspace)
    record = next((tmp_path / "docs/assets/terminal").glob("*.txt")).read_text(encoding="utf-8")
    assert "PRODUCTION_FIREBASE_SESSION_STARTUP_AND_LOGIN_UI=PASS" in record
    assert "PRIVATE-ACCOUNT-TEXT" not in record and "<hierarchy>" not in record
    assert (tmp_path / "docs/assets/hardware/family-app/05-production-login.png").read_bytes() == PNG


def test_debug_flag_is_required_for_the_debuggable_build_and_warns(workspace, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["install_test_family_app.py", "--production-only", "--debug", "--apply"]
    )
    install.main()
    assert installed(workspace) == ["family-debug.apk"]
    assert "WARNING=debuggable build replaces the installed release app" in capsys.readouterr().out


def test_release_flag_stays_accepted_as_a_no_op_preview(workspace, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["install_test_family_app.py", "--production-only", "--release"])
    install.main()
    assert installed(workspace) == []
    assert "PREVIEW=family-release.apk;" in capsys.readouterr().out


def test_debug_and_release_together_is_a_usage_error(workspace, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["install_test_family_app.py", "--production-only", "--debug", "--release"]
    )
    with pytest.raises(SystemExit):
        install.main()
    assert installed(workspace) == []


def test_fixture_run_previews_release_rather_than_debug_over_the_signed_in_app(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    build(tmp_path, ["family-debug.apk", "family-release.apk", "family-fixture.apk", "family-test.apk"])
    monkeypatch.setattr(sys, "argv", ["install_test_family_app.py"])
    install.main()
    assert "PREVIEW=family-release.apk, family-fixture.apk, family-test.apk;" in capsys.readouterr().out


def release_apk(root):
    folder = root / "tmp/family-app-build"
    folder.mkdir(parents=True)
    apk = folder / "family-release.apk"
    with zipfile.ZipFile(apk, "w") as archive:
        archive.writestr(
            "classes.dex",
            "1:123456789012:android:unit unit-project 123456789012 unit-api-key "
            "unit.apps.googleusercontent.com",
        )
        archive.writestr("AndroidManifest.xml", "binary")
    (folder / "build.json").write_text(
        json.dumps({"family-release.apk": hashlib.sha256(apk.read_bytes()).hexdigest()})
    )
    private = root / ".deploy/family-app"
    private.mkdir(parents=True)
    (private / "tools.json").write_text(json.dumps({"java_home": "jdk", "sdk": "sdk"}))
    (private / "signing.json").write_text(json.dumps({"sha256": "AA:" * 31 + "AA"}))
    (private / "google-services.json").write_text(json.dumps(FIREBASE))


def apk_tools(debuggable):
    """Fake apksigner/aapt2 answers keyed on the command shape verify_family_apk.py uses."""

    def run(command, **kwargs):
        if "apksigner.jar" in command[2]:
            out = "Signer #1 certificate SHA-256 digest: " + "aa" * 32 + "\n"
        elif command[1:3] == ["dump", "permissions"]:
            out = "uses-permission: name='android.permission.POST_NOTIFICATIONS'\n"
        elif command[1:3] == ["dump", "badging"]:
            out = "package: name='com.aircon.family'\n" + ("application-debuggable\n" if debuggable else "")
        elif command[1:3] == ["dump", "resources"]:
            out = (
                "resource 0x7f0a0001 xml/network_security_config () (file) "
                "res/xml/network_security_config.xml type=XML\n"
            )
        elif command[-1] == "AndroidManifest.xml":
            out = (
                "A: networkSecurityConfig(0x01010527)=@0x7f0a0001\n"
                "E: service FamilyMessagingService\n"
                "E: meta-data firebase_messaging_auto_init_enabled\n"
            )
        else:
            out = 'A: cleartextTrafficPermitted=false\nE: certificates src="system"\n'
        return subprocess.CompletedProcess(command, 0, out, "")

    return run


class Recorder:
    def __init__(self):
        self.lines = []

    def log(self, value):
        self.lines.append(value)


def test_release_apk_verification_rejects_a_debuggable_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release_apk(tmp_path)
    recorder = Recorder()
    monkeypatch.setattr(verify, "PhoneSession", lambda label: recorder)
    monkeypatch.setattr(verify.subprocess, "run", apk_tools(debuggable=True))
    with pytest.raises(RuntimeError, match="Release APK is debuggable"):
        verify.main()
    assert "FAMILY_APK_VERIFICATION=PASS" not in recorder.lines


def test_release_apk_verification_passes_a_non_debuggable_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release_apk(tmp_path)
    recorder = Recorder()
    monkeypatch.setattr(verify, "PhoneSession", lambda label: recorder)
    monkeypatch.setattr(verify.subprocess, "run", apk_tools(debuggable=False))
    verify.main()
    assert "FAMILY_APK_VERIFICATION=PASS" in recorder.lines
    assert any("APPLICATION_DEBUGGABLE=FALSE" in line for line in recorder.lines)
