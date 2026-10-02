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
    assert hashlib.sha256(apk.read_bytes()).hexdigest() == expected
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
    assert fingerprint.lower() == signing["sha256"].replace(":", "").lower()
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
    assert result.returncode == 0 and b"Success" in result.stdout
    installed = adb.run("-s", endpoint, "shell", "pm", "path", "com.aircon.family", timeout=15)
    paths = [
        s.removeprefix("package:")
        for s in installed.stdout.decode().splitlines()
        if s.startswith("package:")
    ]
    assert installed.returncode == 0 and len(paths) == 1
    actual = adb.run("-s", endpoint, "exec-out", "sha256sum", paths[0], timeout=20)
    assert actual.returncode == 0 and actual.stdout.decode().split()[0] == expected
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
        assert done.returncode == 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
