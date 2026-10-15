"""The release smoke test must read the restarted client's UI without leaving a dump on the phone."""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "scripts/android"
sys.path.insert(0, str(SCRIPTS))
import a50_adb  # noqa: E402
import run_a50_family_smoke as smoke  # noqa: E402

ENDPOINT = "192.0.2.1:43210"
CAPTURE_ROOT = "/storage/emulated/0/Android/data/com.aircon.family/files/test-captures"
PNG = b"\x89PNG\r\n\x1a\nunit"
RESTARTED_UI = (
    '<hierarchy><node package="com.aircon.family" text="Unit Home"/>'
    '<node package="com.aircon.family" text="새 집 만들기"/>'
    '<node package="com.aircon.family" text="PRIVATE-ACCOUNT-TEXT"/></hierarchy>'
).encode("utf-8")


def workspace(root):
    (root / "docs/assets/hardware/family-app").mkdir(parents=True)
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
    tools = root / ".deploy/family-app"
    tools.mkdir()
    (tools / "tools.json").write_text(json.dumps({"java_home": "jdk", "sdk": "sdk"}))
    (tools / "signing.json").write_text(json.dumps({"sha256": "AA:" * 31 + "AA"}))
    smoke_root = root / "tmp/family-app-smoke-tests"
    smoke_root.mkdir(parents=True)
    (smoke_root / "family-production-test.apk").write_bytes(b"unit smoke apk")
    (smoke_root / "build.json").write_text(
        json.dumps({"family-production-test.apk": hashlib.sha256(b"unit smoke apk").hexdigest()})
    )
    build_root = root / "tmp/family-app-build"
    build_root.mkdir()
    (build_root / "family-release.apk").write_bytes(b"unit release apk")
    release_hash = hashlib.sha256(b"unit release apk").hexdigest()
    (build_root / "build.json").write_text(json.dumps({"family-release.apk": release_hash}))
    return release_hash


def apk_tools(command, **kwargs):
    if "apksigner.jar" in command[2]:
        out = "Signer #1 certificate SHA-256 digest: " + "aa" * 32 + "\n"
    else:
        out = 'A: android:targetPackage="com.aircon.family"\nE: instrumentation com.aircon.family.test\n'
    return subprocess.CompletedProcess(command, 0, out, "")


def test_post_restart_ui_is_read_privately_and_removed_from_the_phone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    release_hash = workspace(tmp_path)
    calls = []

    def run(self, *args, timeout=10):
        calls.append(args)
        reply = b""
        if args[2:6] == ("shell", "pm", "path", "com.aircon.family"):
            reply = b"package:/data/app/unit/base.apk\n"
        elif args[2:4] == ("exec-out", "sha256sum"):
            reply = release_hash.encode() + b"  base.apk\n"
        elif args[2:4] == ("install", "-r"):
            reply = b"Success\n"
        elif args[2:5] == ("shell", "am", "instrument"):
            reply = ("INSTRUMENTATION_STATUS: capture_root=" + CAPTURE_ROOT + "\nOK (1 test)\n").encode()
        elif args[2:4] == ("exec-out", "cat"):
            reply = PNG
        elif args[2] == "exec-out" and "uiautomator dump" in args[3]:
            reply = RESTARTED_UI
        return subprocess.CompletedProcess(args, 0, reply, b"")

    monkeypatch.setattr(a50_adb.A50ADB, "run", run)
    monkeypatch.setattr(a50_adb.A50ADB, "connect", lambda self, timeout=30, **kwargs: ENDPOINT)
    monkeypatch.setattr(smoke.subprocess, "run", apk_tools)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        sys, "argv", ["run_a50_family_smoke.py", "--home-name", "Unit Home", "--apply"]
    )
    smoke.main()
    dumps = [args for args in calls if "uiautomator" in " ".join(args)]
    assert len(dumps) == 1 and dumps[0][2] == "exec-out"
    assert "rm -f /data/local/tmp/family-post-restart.xml" in dumps[0][3]
    assert not any(args[2:5] == ("shell", "uiautomator", "dump") for args in calls)
    record = next((tmp_path / "docs/assets/terminal").glob("*.txt")).read_text(encoding="utf-8")
    assert "SIGNED_RELEASE_REAL_LOGIN_HTTPS_HOME_AND_CLIENT_RESTART=PASS" in record
    assert "PRIVATE-ACCOUNT-TEXT" not in record and "<hierarchy>" not in record
    assert (tmp_path / "docs/assets/hardware/family-app/08-a50-real-test-home.png").read_bytes() == PNG
