"""Validate a downloaded Firebase Android configuration and keep it outside Git."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from a50_record import PhoneSession


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    firebase = json.loads(args.source.read_text(encoding="utf-8-sig"))
    if firebase["project_info"]["project_id"] != args.project_id:
        raise RuntimeError("Downloaded Firebase project differs from the chosen project")
    client = next(
        (
            c
            for c in firebase["client"]
            if c["client_info"]["android_client_info"]["package_name"] == "com.aircon.family"
        ),
        None,
    )
    if client is None:
        raise RuntimeError("Registered family Android package missing")
    private = Path(".deploy/family-app")
    signing = json.loads((private / "signing.json").read_text())
    expected_sha1 = signing["sha1"].replace(":", "").lower()
    oauth = client.get("oauth_client", [])
    if not any(
        c["client_type"] == 1
        and c.get("android_info", {}).get("package_name") == "com.aircon.family"
        and c["android_info"].get("certificate_hash", "").lower() == expected_sha1
        for c in oauth
    ):
        raise RuntimeError("Android OAuth signing SHA-1 missing; register it and download again")
    if not any(
        c["client_type"] == 3 and c.get("client_id", "").endswith(".apps.googleusercontent.com")
        for c in oauth
    ):
        raise RuntimeError("Google OAuth web client missing")
    if not client["api_key"][0]["current_key"] or not client["client_info"]["mobilesdk_app_id"]:
        raise RuntimeError("Firebase client configuration incomplete")
    target = private / "google-services.json"
    if target.exists() and json.loads(target.read_text(encoding="utf-8-sig")) != firebase:
        raise RuntimeError("Existing private configuration differs; preserved for inspection")
    if args.source.resolve() != target.resolve():
        shutil.copyfile(args.source, target)
    PhoneSession("family-firebase-config-import").log(
        "$ import_family_firebase.py --source [user download] --project-id [REDACTED]\n"
        "FIREBASE_PROJECT_ANDROID_PACKAGE_AND_SIGNING_SHA1=PASS\n"
        "GOOGLE_OAUTH_WEB_CLIENT_AND_SDK_CONFIGURATION=PASS\n"
        "PRIVATE_CONFIGURATION=READY SOURCE_ORIGINAL=PRESERVED VALUES=NOT_PRINTED"
    )


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
