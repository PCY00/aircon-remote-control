"""Verify actual APK signatures, permissions and production/fixture separation."""

import hashlib
import json
import re
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
            encoding="utf-8",
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
            encoding="utf-8",
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
            firebase = json.loads((private / "google-services.json").read_text())
            client = next(
                c
                for c in firebase["client"]
                if c["client_info"]["android_client_info"]["package_name"] == "com.aircon.family"
            )
            expected_config = [
                client["client_info"]["mobilesdk_app_id"],
                firebase["project_info"]["project_id"],
                firebase["project_info"]["project_number"],
                client["api_key"][0]["current_key"],
                next(c["client_id"] for c in client["oauth_client"] if c["client_type"] == 3),
            ]
            with zipfile.ZipFile(apk) as archive:
                assert "assets/test-fixture.json" not in archive.namelist(), (
                    "Fixture assets in production APK"
                )
                dex_files = []
                for entry in archive.namelist():
                    if entry.endswith(".dex"):
                        data = archive.read(entry)
                        dex_files.append(data)
                        for marker in (b"owner@example.test", b"fixture-owner", b"family_token"):
                            assert marker not in data, "Fixture identity code in production APK"
                for value in expected_config:
                    if not any(value.encode("utf-8") in data for data in dex_files):
                        raise RuntimeError(
                            "Actual Firebase configuration missing from production APK"
                        )
            record.log("PRODUCTION_APK_FIXTURE_IDENTITY_AND_TOKEN_ASSETS=ABSENT")
            record.log(
                "ACTUAL_FIREBASE_APP_PROJECT_API_KEY_AND_WEB_CLIENT_IN_APK=PASS VALUES=PRIVATE"
            )
            resources = subprocess.run(
                [str(buildtools / "aapt2.exe"), "dump", "resources", str(apk)],
                capture_output=True,
                encoding="utf-8",
                check=True,
            ).stdout
            mapping = re.search(
                r"resource (0x[0-9a-f]+) xml/network_security_config\s+"
                r"\(\) \(file\) (res/\S+) type=XML",
                resources,
            )
            if mapping is None:
                raise RuntimeError("Compiled network policy resource missing")
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
                encoding="utf-8",
                check=True,
            ).stdout
            if not any(
                "networkSecurityConfig" in line and mapping[1] in line
                for line in manifest.splitlines()
            ):
                raise RuntimeError("Manifest does not reference the checked network policy")
            assert 'android.permission.POST_NOTIFICATIONS' in permissions
            assert 'FamilyMessagingService' in manifest
            assert 'firebase_messaging_auto_init_enabled' in manifest
            record.log('FCM_SENDER_CONFIGURATION_NOTIFICATION_PERMISSION_AND_PRIVATE_RECEIVER=PASS')
            network = subprocess.run(
                [
                    str(buildtools / "aapt2.exe"),
                    "dump",
                    "xmltree",
                    str(apk),
                    "--file",
                    mapping[2],
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            ).stdout
            if "cleartextTrafficPermitted=false" not in network or 'src="system"' not in network:
                raise RuntimeError("HTTPS and system trust policy missing")
            if name == "family-release.apk" and "cleartextTrafficPermitted=true" in network:
                raise RuntimeError("Release APK permits cleartext HTTP")
            record.log("MANIFEST_NETWORK_POLICY_REFERENCE_AND_HTTPS_BASE=PASS")
            record.log(
                "$ aapt2 dump xmltree " + name + " [network security configuration]\n" + network
            )
    record.log("FAMILY_APK_VERIFICATION=PASS")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
