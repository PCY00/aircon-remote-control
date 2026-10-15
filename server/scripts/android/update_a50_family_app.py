"""Data-preserving signed APK update; never clears the real Google login."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from a50_adb import A50ADB
from a50_record import PhoneSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path("tmp/family-app-build")
    apk = root / "family-release.apk"
    expected = json.loads((root / "build.json").read_text())["family-release.apk"]
    if hashlib.sha256(apk.read_bytes()).hexdigest() != expected:
        raise RuntimeError("APK changed since build; no phone action taken.")
    tools = json.loads(Path(".deploy/family-app/tools.json").read_text())
    signing = json.loads(Path(".deploy/family-app/signing.json").read_text())
    output = subprocess.run(
        [
            str(Path(tools["java_home"]) / "bin/java.exe"),
            "-jar",
            str(Path(tools["sdk"]) / "build-tools/36.0.0/lib/apksigner.jar"),
            "verify",
            "--print-certs",
            str(apk),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    fingerprint = next(
        line.split(": ", 1)[1]
        for line in output.splitlines()
        if "certificate SHA-256 digest:" in line
    )
    if fingerprint.lower() != signing["sha256"].replace(":", "").lower():
        raise RuntimeError("APK signing certificate differs; no phone action taken.")
    badging = subprocess.run(
        [str(Path(tools["sdk"]) / "build-tools/36.0.0/aapt2.exe"), "dump", "badging", str(apk)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    if "application-debuggable" in badging:
        raise RuntimeError("APK is debuggable; run-as could read app data. No phone action taken.")
    if not args.apply:
        print(
            "PLAN=verified_same_certificate_release; install_-r; "
            "Google_session_and_app_data_preserved"
        )
        print("PREVIEW_ONLY=NO_DEVICE_MUTATION")
        return
    record = PhoneSession("family-fcm-apk-update")
    adb = A50ADB(Path(".deploy/a50/adb.json"))
    endpoint = adb.connect(timeout=40)
    result = adb.run("-s", endpoint, "install", "-r", str(apk.resolve()), timeout=120)
    record.log(
        "$ adb [verified A50] install -r verified family-release.apk\n"
        + result.stdout.decode()
        + result.stderr.decode()
        + "\nEXIT_CODE="
        + str(result.returncode)
    )
    if result.returncode or b"Success" not in result.stdout:
        raise RuntimeError("APK update was not accepted; inspect before retrying.")
    installed = adb.run("-s", endpoint, "shell", "pm", "path", "com.aircon.family", timeout=15)
    paths = [
        s.removeprefix("package:")
        for s in installed.stdout.decode().splitlines()
        if s.startswith("package:")
    ]
    if installed.returncode or len(paths) != 1:
        raise RuntimeError("Installed APK path unavailable; inspect before retrying.")
    actual = adb.run("-s", endpoint, "exec-out", "sha256sum", paths[0], timeout=20)
    if actual.returncode or actual.stdout.decode().split()[:1] != [expected]:
        raise RuntimeError("Installed APK differs from the verified local release.")
    record.log("INSTALLED_PRODUCTION_APK_EQUALS_LOCAL_VERIFIED_RELEASE=PASS DATA_NOT_CLEARED=TRUE")
    for command, label in [
        (("shell", "input", "keyevent", "224"), "wake for own app test"),
        (
            ("shell", "am", "start", "-W", "-n", "com.aircon.family/.MainActivity"),
            "open updated own app",
        ),
    ]:
        done = adb.run("-s", endpoint, *command, timeout=25)
        record.log(
            "$ adb [verified A50] " + label + "\n" + done.stdout.decode() + done.stderr.decode()
        )
        if done.returncode:
            raise RuntimeError("Phone step failed; later steps were not run.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
