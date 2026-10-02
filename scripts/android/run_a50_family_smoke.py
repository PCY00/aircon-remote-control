"""Test the user's signed-in release APK; preserve its binary, account, and existing homes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from a50_adb import A50ADB
from a50_record import PhoneSession


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home-name", required=True, help="User-approved real test home name")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument('--push-test', choices=('registerRealInstallation','receiveRealFCMWhileBackgrounded'))
    args = parser.parse_args()
    if not 1 <= len(args.home_name) <= 80 or any(ord(c) < 32 for c in args.home_name):
        parser.error("Home name must contain 1–80 printable characters")
    root = Path("tmp/family-app-smoke-tests")
    original = Path("tmp/family-app-build")
    hashes = json.loads((root / "build.json").read_text())
    release_hash = json.loads((original / "build.json").read_text())["family-release.apk"]
    apk = root / "family-production-test.apk"
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == hashes[apk.name]
    assert (
        hashlib.sha256((original / "family-release.apk").read_bytes()).hexdigest() == release_hash
    )
    private = Path(".deploy/family-app")
    tools = json.loads((private / "tools.json").read_text())
    signing = json.loads((private / "signing.json").read_text())
    buildtools = Path(tools["sdk"]) / "build-tools/36.0.0"
    signed = subprocess.run(
        [
            str(Path(tools["java_home"]) / "bin/java.exe"),
            "-jar",
            str(buildtools / "lib/apksigner.jar"),
            "verify",
            "--print-certs",
            str(apk),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    actual = next(
        line.split(": ", 1)[1]
        for line in signed.splitlines()
        if "certificate SHA-256 digest:" in line
    )
    assert actual.lower() == signing["sha256"].replace(":", "").lower()
    manifest = subprocess.run(
        [
            str(buildtools / "aapt2.exe"),
            "dump",
            "xmltree",
            str(apk),
            "--file",
            "AndroidManifest.xml",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    assert "android:targetPackage" in manifest and 'com.aircon.family"' in manifest
    assert "com.aircon.family.test" in manifest
    print("SMOKE_APK_HASH_SIGNATURE_AND_EXACT_TARGET=PASS DELIVERED_RELEASE_HASH_UNCHANGED=TRUE")
    if not args.apply:
        print("PREVIEW_ONLY=NO_DEVICE_MUTATION")
        print(
            "PLAN=install_signed_test_apk; use_existing_Google_session; "
            "create_or_reuse_named_home; capture_redacted_owner_UI"
        )
        return
    record = PhoneSession("family-real-release-smoke")
    adb = A50ADB(Path(".deploy/a50/adb.json"))
    endpoint = adb.connect(timeout=40)

    def run(arguments, label, timeout=30):
        result = adb.run("-s", endpoint, *arguments, timeout=timeout)
        record.log(
            "$ adb [verified A50] "
            + label
            + "\n"
            + (result.stdout + result.stderr).decode("utf-8", errors="replace")
            + "\nEXIT_CODE="
            + str(result.returncode)
        )
        if result.returncode:
            raise RuntimeError("Native production smoke step failed; stop and inspect.")
        return result.stdout

    # Read the installation location privately; publish the comparison result only.
    located = adb.run("-s", endpoint, "shell", "pm", "path", "com.aircon.family", timeout=15)
    paths = [
        line.removeprefix("package:")
        for line in located.stdout.decode().splitlines()
        if line.startswith("package:")
    ]
    assert located.returncode == 0 and len(paths) == 1
    digest = adb.run("-s", endpoint, "exec-out", "sha256sum", paths[0], timeout=20)
    assert digest.returncode == 0 and digest.stdout.decode().split()[0] == release_hash
    record.log("INSTALLED_PRODUCTION_APK_EQUALS_PREVIOUSLY_DELIVERED_RELEASE=PASS")
    run(
        ["install", "-r", str(apk.resolve())],
        "install -r signed production instrumentation test APK",
        120,
    )
    encoded = base64.b64encode(args.home_name.encode()).decode()
    output = run(
        [
            "shell",
            "am",
            "instrument",
            "-w",
            "-e",
            "class",
            ('com.aircon.family.OwnPushSmokeTest#'+args.push_test if args.push_test else 'com.aircon.family.OwnFamilySmokeTest'),
            "-e",
            "home_name_b64",
            encoded,
            "com.aircon.family.test/androidx.test.runner.AndroidJUnitRunner",
        ],
        "native UI smoke [user-approved home; existing real Google session; no token extraction]",
        120,
    )
    if not re.search(rb"OK \(1 tests?\)", output):
        raise RuntimeError(
            "Native real-account smoke did not report success; inspect before retry."
        )
    images = Path("docs/assets/hardware/family-app")
    roots = re.findall(rb"INSTRUMENTATION_STATUS: capture_root=([^\r\n]+)", output)
    assert roots and len(set(roots)) == 1
    capture_root = roots[0].decode("utf-8")
    assert re.fullmatch(
        r"/storage/emulated/\d+/Android/data/com\.aircon\.family/files/test-captures", capture_root
    )
    captures = (("10-a50-fcm-installation-registered",) if args.push_test=='registerRealInstallation' else
                ("11-a50-fcm-background-receipt",) if args.push_test else
                ("08-a50-real-test-home", "09-a50-real-owner-members-redacted"))
    for name in captures:
        result = adb.run(
            "-s",
            endpoint,
            "exec-out",
            "cat",
            capture_root + "/" + name + ".png",
            timeout=15,
        )
        assert result.returncode == 0 and result.stdout.startswith(b"\x89PNG")
        (images / (name + ".png")).write_bytes(result.stdout)
        record.log(
            "ACTUAL_REAL_ACCOUNT_UI_CAPTURE=" + name + ".png EMAIL_REDACTED_BEFORE_EXPORT=TRUE"
        )
    run(
        ["shell", "am", "force-stop", "com.aircon.family"],
        "restart own family client only [server continues]",
    )
    run(
        ["shell", "am", "start", "-W", "-n", "com.aircon.family/.MainActivity"],
        "reopen original release APK [verify saved Google session and HTTPS origin]",
    )
    time.sleep(2)
    run(
        ["shell", "uiautomator", "dump", "/data/local/tmp/family-post-restart.xml"],
        "read own client UI after restart",
    )
    result = adb.run(
        "-s", endpoint, "exec-out", "cat", "/data/local/tmp/family-post-restart.xml", timeout=15
    )
    assert result.returncode == 0
    tree = ET.fromstring(result.stdout)
    texts = {
        node.get("text") for node in tree.iter("node") if node.get("package") == "com.aircon.family"
    }
    assert args.home_name in texts and "새 집 만들기" in texts
    record.log('SIGNED_RELEASE_REAL_LOGIN_HTTPS_HOME_AND_CLIENT_RESTART=PASS TEST='+str(args.push_test or 'household_ui'))
    record.log(
        "GOOGLE_TOKENS_PASSWORDS_AND_EXISTING_HOME_DATA=NOT_EXPORTED_OR_DELETED"
    )


if __name__ == "__main__":
    main()
