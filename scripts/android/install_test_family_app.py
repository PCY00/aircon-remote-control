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
    parser.add_argument(
        "--production-only",
        action="store_true",
        help="Install and capture the Google-login APK without fixture tests",
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="With --production-only, install the verified release APK",
    )
    args = parser.parse_args()
    if args.release and not args.production_only:
        parser.error("--release requires --production-only")
    root = Path("tmp/family-app-build")
    hashes = json.loads((root / "build.json").read_text())
    for name, expected in hashes.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Built APK changed; inspect")
    production_name = "family-release.apk" if args.release else "family-debug.apk"
    selected = (
        [production_name]
        if args.production_only
        else [
            name
            for name in ("family-debug.apk", "family-fixture.apk", "family-test.apk")
            if name in hashes
        ]
    )
    if args.production_only and production_name not in hashes:
        raise RuntimeError("Production APK missing; build actual Firebase configuration first")
    if not args.production_only and not {"family-fixture.apk", "family-test.apk"}.issubset(hashes):
        raise RuntimeError(
            "Use --production-only, or build --tests with a running isolated fixture"
        )
    if not args.apply:
        print("PREVIEW=" + ", ".join(selected) + "; install -r preserves app data")
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

    for name in selected:
        run(("install", "-r", str((root / name).resolve())), "install -r " + name, 120)
    if not args.production_only:
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
            run(
                ("shell", "input", "keyevent", "223"),
                "screen off [restore server phone screen state]",
            )
    if not args.production_only and b"OK (2 tests)" not in output:
        raise RuntimeError("Instrumentation did not report both tests passed")
    images = Path("docs/assets/hardware/family-app")
    images.mkdir(parents=True, exist_ok=True)
    for name in (
        "01-fixture-homes",
        "02-fixture-new-home",
        "03-fixture-members",
        "04-fixture-logout",
    ):
        if args.production_only:
            break
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
    if args.production_only or "family-debug.apk" in hashes:
        try:
            run(("shell", "input", "keyevent", "224"), "screen on [own app capture]")
            run(
                ("shell", "am", "start", "-W", "-n", "com.aircon.family/.MainActivity"),
                "am start [production Google-login APK]",
            )
            import time

            time.sleep(2)
            run(
                ("shell", "uiautomator", "dump", "/data/local/tmp/family-production-ui.xml"),
                "uiautomator dump [own production app startup verification]",
            )
            ui = adb.run(
                "-s",
                endpoint,
                "exec-out",
                "cat",
                "/data/local/tmp/family-production-ui.xml",
                timeout=15,
            )
            if ui.returncode or not all(
                value.encode() in ui.stdout
                for value in ("com.aircon.family", "우리 집을 함께", "Google로 계속하기")
            ):
                raise RuntimeError("Production login UI did not appear; inspect own app startup")
            record.log("PRODUCTION_FIREBASE_SESSION_STARTUP_AND_LOGIN_UI=PASS")
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
    if args.production_only:
        record.log("FAMILY_PRODUCTION_APK_INSTALL_AND_STARTUP=PASS REAL_GOOGLE_LOGIN=NOT_TESTED")
    else:
        record.log("FAMILY_NATIVE_ANDROID_UI_AND_API_TESTS=PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
