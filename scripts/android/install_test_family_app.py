"""Preview or install verified family APKs and run isolated native Android tests."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from a50_adb import A50ADB
from a50_record import PhoneSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path("tmp/family-app-build")
    hashes = json.loads((root / "build.json").read_text())
    for name, expected in hashes.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Built APK changed; inspect")
    if not args.apply:
        print("PREVIEW=" + ", ".join(hashes) + "; install -r preserves app data")
        print("PERMISSIONS=inspect verify_family_apk.py output; management APK/settings untouched")
        return
    record = PhoneSession("family-native-apk-tests")
    adb = A50ADB(Path(".deploy/a50/adb.json"))
    endpoint = adb.connect(timeout=40)

    def run(arguments, label, timeout=60):
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
            raise RuntimeError("Native app step failed; later steps stopped.")
        return result.stdout

    for name in ("family-debug.apk", "family-fixture.apk", "family-test.apk"):
        if name not in hashes:
            continue
        run(("install", "-r", str((root / name).resolve())), "install -r " + name, 120)
    try:
        run(("shell", "input", "keyevent", "224"), "screen on [isolated UI test]")
        output = run(
            (
                "shell",
                "am",
                "instrument",
                "-w",
                "com.aircon.family.fixture.test/androidx.test.runner.AndroidJUnitRunner",
            ),
            "am instrument [isolated fixture APK; real Android UI and API tests]",
            180,
        )
    finally:
        run(("shell", "input", "keyevent", "3"), "home [restore server phone home screen]")
        run(("shell", "input", "keyevent", "223"), "screen off [restore server phone screen state]")
    if b"OK (2 tests)" not in output:
        raise RuntimeError("Instrumentation did not report both tests passed")
    images = Path("docs/assets/hardware/family-app")
    images.mkdir(parents=True, exist_ok=True)
    for name in (
        "01-fixture-homes",
        "02-fixture-new-home",
        "03-fixture-members",
        "04-fixture-logout",
    ):
        result = adb.run(
            "-s",
            endpoint,
            "exec-out",
            "run-as",
            "com.aircon.family.fixture",
            "cat",
            "files/" + name + ".png",
            timeout=15,
        )
        if result.returncode or not result.stdout.startswith(b"\x89PNG"):
            raise RuntimeError("Fixture capture missing")
        (images / (name + ".png")).write_bytes(result.stdout)
        record.log("ACTUAL_ANDROID_UI_CAPTURE=" + name + ".png IDENTITY=fictional_fixture")
    if "family-debug.apk" in hashes:
        try:
            run(("shell", "input", "keyevent", "224"), "screen on [own app capture]")
            run(
                ("shell", "am", "start", "-W", "-n", "com.aircon.family/.MainActivity"),
                "am start [production Google-login APK]",
            )
            import time

            time.sleep(2)
            result = adb.run("-s", endpoint, "exec-out", "screencap", "-p", timeout=15)
            if result.returncode or not result.stdout.startswith(b"\x89PNG"):
                raise RuntimeError("Production capture failed")
            (images / "05-production-login.png").write_bytes(result.stdout)
            record.log(
                "ACTUAL_PRODUCTION_LOGIN_SCREEN=CAPTURED REAL_GOOGLE_ACCOUNT_LOGIN=NOT_TESTED"
            )
        finally:
            run(("shell", "input", "keyevent", "3"), "home [restore server phone home screen]")
            run(
                ("shell", "input", "keyevent", "223"),
                "screen off [restore server phone screen state]",
            )
    record.log("FAMILY_NATIVE_ANDROID_UI_AND_API_TESTS=PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
