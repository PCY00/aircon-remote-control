"""Stage local Android sources in an ASCII build path; keep cloud/signing config out of Git."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from a50_record import PhoneSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true")
    parser.add_argument(
        "--production-smoke-only",
        action="store_true",
        help="Build only signed UI smoke-test APK; preserve previously delivered production APKs",
    )
    parser.add_argument(
        "--fixture-only",
        action="store_true",
        help="Build isolated tests without production Firebase configuration",
    )
    args = parser.parse_args()
    if args.production_smoke_only and (args.tests or args.fixture_only):
        parser.error("--production-smoke-only cannot be combined with fixture options")
    record = PhoneSession("family-apk-build")
    private = Path(".deploy/family-app")
    tools = json.loads((private / "tools.json").read_text())
    signing = json.loads((private / "signing.json").read_text())
    firebase = (
        json.loads((private / "google-services.json").read_text())
        if not args.fixture_only
        else {
            "project_info": {"project_id": "test-project"},
            "client": [
                {
                    "client_info": {
                        "android_client_info": {"package_name": "com.aircon.family"},
                        "mobilesdk_app_id": "1:123456789:android:fixture",
                    },
                    "oauth_client": [
                        {"client_type": 3, "client_id": "fixture.apps.googleusercontent.com"}
                    ],
                    "api_key": [{"current_key": "fixture-key"}],
                }
            ],
        }
    )
    client = next(
        c
        for c in firebase["client"]
        if c["client_info"]["android_client_info"]["package_name"] == "com.aircon.family"
    )
    web = next(c["client_id"] for c in client["oauth_client"] if c["client_type"] == 3)
    config = {k: signing[k] for k in ("signing_file", "signing_password_file")}
    config.update(
        FIREBASE_APP_ID=client["client_info"]["mobilesdk_app_id"],
        FIREBASE_API_KEY=client["api_key"][0]["current_key"],
        FIREBASE_PROJECT_ID=firebase["project_info"]["project_id"],
        GOOGLE_WEB_CLIENT_ID=web,
    )
    root = Path.home() / ".codex/family-android-build"
    root.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="project-", dir=root))
    source = Path("android/family-app")
    for path in source.rglob("*"):
        if path.is_file():
            target = stage / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    (stage / "private-build.json").write_text(json.dumps(config))
    (stage / "local.properties").write_text("sdk.dir=" + tools["sdk"].replace("\\", "/") + "\n")
    if args.tests or args.fixture_only:
        fixture = private / "test-fixture.json"
        target = stage / "app/src/fixture/assets/test-fixture.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, target)
    env = dict(os.environ, JAVA_HOME=tools["java_home"], ANDROID_HOME=tools["sdk"])
    tasks = [
        "testProductionDebugUnitTest",
        "assembleProductionDebug",
        "assembleProductionRelease",
    ] + (["assembleFixtureDebug", "assembleFixtureDebugAndroidTest"] if args.tests else [])
    if args.fixture_only:
        tasks = [
            "testFixtureDebugUnitTest",
            "assembleFixtureDebug",
            "assembleFixtureDebugAndroidTest",
        ]
    if args.production_smoke_only:
        tasks = ["assembleProductionDebugAndroidTest"]
    command = [
        str(Path(tools["java_home"]) / "bin/java.exe"),
        "-Dfile.encoding=UTF-8",
        "-Dsun.stdout.encoding=UTF-8",
        "-Dsun.stderr.encoding=UTF-8",
        "-classpath",
        str(Path(tools["gradle"]) / "lib/gradle-launcher-8.13.jar"),
        "org.gradle.launcher.GradleMain",
        "--no-daemon",
        "--console=plain",
        *tasks,
    ]
    result = subprocess.run(
        command,
        cwd=stage,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
    )
    safe = result.stdout + result.stderr
    for value in list(config.values()) + [str(Path.home()), str(Path.cwd())]:
        safe = safe.replace(value, "[REDACTED_BUILD_CONFIG]")
        safe = safe.replace(value.replace("\\", "/"), "[REDACTED_BUILD_CONFIG]")
    record.log(
        "$ Gradle 8.13 "
        + " ".join(tasks)
        + " [ASCII staging, private configuration]\n"
        + safe
        + "\nEXIT_CODE="
        + str(result.returncode)
    )
    if result.returncode:
        raise RuntimeError("Family APK build failed; inspect sanitized build record.")
    output = Path(
        "tmp/family-app-smoke-tests" if args.production_smoke_only else "tmp/family-app-build"
    )
    output.mkdir(exist_ok=True)
    verified = {}
    artifacts = (
        []
        if args.fixture_only
        else [
            ("family-debug.apk", "app/build/outputs/apk/production/debug/app-production-debug.apk"),
            (
                "family-release.apk",
                "app/build/outputs/apk/production/release/app-production-release.apk",
            ),
        ]
        + (
            [
                ("family-fixture.apk", "app/build/outputs/apk/fixture/debug/app-fixture-debug.apk"),
                (
                    "family-test.apk",
                    "app/build/outputs/apk/androidTest/fixture/debug/app-fixture-debug-androidTest.apk",
                ),
            ]
            if args.tests
            else []
        )
    )
    if args.fixture_only:
        artifacts = [
            ("family-fixture.apk", "app/build/outputs/apk/fixture/debug/app-fixture-debug.apk"),
            (
                "family-test.apk",
                "app/build/outputs/apk/androidTest/fixture/debug/app-fixture-debug-androidTest.apk",
            ),
        ]
    if args.production_smoke_only:
        artifacts = [
            (
                "family-production-test.apk",
                "app/build/outputs/apk/androidTest/production/debug/app-production-debug-androidTest.apk",
            )
        ]
    for name, relative in artifacts:
        apk = stage / relative
        shutil.copyfile(apk, output / name)
        verified[name] = hashlib.sha256(apk.read_bytes()).hexdigest()
        record.log(
            "SIGNED_APK=" + name + " BYTES=" + str(apk.stat().st_size) + " SHA256=" + verified[name]
        )
    (output / "build.json").write_text(json.dumps(verified, indent=2))
    (
        private / ("last-smoke-build.json" if args.production_smoke_only else "last-build.json")
    ).write_text(json.dumps({"stage": str(stage), "fixture_only": args.fixture_only}))
    record.log("FAMILY_APK_BUILD=PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
