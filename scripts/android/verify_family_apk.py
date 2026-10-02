"""Verify actual APK signatures, permissions and production/fixture separation."""

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from a50_record import PhoneSession


def main():
    root = Path("tmp/family-app-build")
    hashes = json.loads((root / "build.json").read_text())
    private = Path(".deploy/family-app")
    tools = json.loads((private / "tools.json").read_text())
    signing = json.loads((private / "signing.json").read_text())
    buildtools = Path(tools["sdk"]) / "build-tools/36.0.0"
    java = Path(tools["java_home"]) / "bin/java.exe"
    record = PhoneSession("family-apk-verification")
    for name, expected in hashes.items():
        apk = root / name
        assert hashlib.sha256(apk.read_bytes()).hexdigest() == expected, "APK changed since build"
        result = subprocess.run(
            [
                str(java),
                "-jar",
                str(buildtools / "lib/apksigner.jar"),
                "verify",
                "--print-certs",
                str(apk),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        actual = next(
            line.split(": ", 1)[1]
            for line in result.stdout.splitlines()
            if "certificate SHA-256 digest:" in line
        )
        assert actual.lower() == signing["sha256"].replace(":", "").lower(), (
            "APK signing key mismatch"
        )
        permissions = subprocess.run(
            [str(buildtools / "aapt2.exe"), "dump", "permissions", str(apk)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        record.log(
            "$ apksigner verify --print-certs "
            + name
            + " [public fingerprint compared privately]\n"
            + "APK_SIGNATURE_AND_EXPECTED_CERTIFICATE=PASS"
        )
        record.log("$ aapt2 dump permissions " + name + "\n" + permissions)
        if name in ("family-debug.apk", "family-release.apk"):
            with zipfile.ZipFile(apk) as archive:
                assert "assets/test-fixture.json" not in archive.namelist(), (
                    "Fixture assets in production APK"
                )
                for entry in archive.namelist():
                    if entry.endswith(".dex"):
                        data = archive.read(entry)
                        for marker in (b"owner@example.test", b"fixture-owner", b"family_token"):
                            assert marker not in data, "Fixture identity code in production APK"
            record.log("PRODUCTION_APK_FIXTURE_IDENTITY_AND_TOKEN_ASSETS=ABSENT")
    record.log("FAMILY_APK_VERIFICATION=PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
