"""Create a dedicated APK key outside Git and privately export its public fingerprints."""

import hashlib
import json
import secrets
import subprocess
from pathlib import Path

from a50_record import PhoneSession


def main():
    record = PhoneSession("family-signing")
    tools = json.loads(Path(".deploy/family-app/tools.json").read_text())
    keytool = str(Path(tools["java_home"]) / "bin/keytool.exe")
    directory = Path.home() / ".codex/device-keys"
    directory.mkdir(parents=True, exist_ok=True)
    key, password = directory / "family-app.p12", directory / "family-app-password.txt"
    if not key.exists():
        if password.exists():
            raise RuntimeError("Password exists without key; inspect.")
        password.write_text(secrets.token_urlsafe(32))
        result = subprocess.run(
            [
                keytool,
                "-genkeypair",
                "-keystore",
                str(key),
                "-storetype",
                "PKCS12",
                "-storepass:file",
                str(password),
                "-alias",
                "family-app",
                "-keyalg",
                "RSA",
                "-keysize",
                "3072",
                "-validity",
                "3650",
                "-dname",
                "CN=Family Smart Home",
            ],
            capture_output=True,
        )
        record.log("DEDICATED_SIGNING_KEY_GENERATION_EXIT=" + str(result.returncode))
        if result.returncode:
            raise RuntimeError("Key generation failed; inspect private outputs.")
    if not password.exists():
        raise RuntimeError("Existing signing password missing; key preserved.")
    result = subprocess.run(
        [
            keytool,
            "-exportcert",
            "-keystore",
            str(key),
            "-storepass:file",
            str(password),
            "-alias",
            "family-app",
        ],
        capture_output=True,
        check=True,
    )

    def fingerprint(algorithm):
        digest = algorithm(result.stdout).hexdigest()
        return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2)).upper()

    private = Path(".deploy/family-app")
    private.mkdir(parents=True, exist_ok=True)
    (private / "signing.json").write_text(
        json.dumps(
            {
                "signing_file": str(key),
                "signing_password_file": str(password),
                "sha1": fingerprint(hashlib.sha1),
                "sha256": fingerprint(hashlib.sha256),
            },
            indent=2,
        )
    )
    record.log(
        "DEDICATED_FAMILY_SIGNING_KEY=READY PRIVATE_KEY_OUTSIDE_REPOSITORY=TRUE\n"
        "PUBLIC_FINGERPRINTS_SAVED_PRIVATELY=TRUE EXISTING_MANAGEMENT_SIGNING_KEY=UNCHANGED"
    )


if __name__ == "__main__":
    main()
