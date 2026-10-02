"""Open the verified A50 for the user to enter Google credentials themselves."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from a50_adb import A50ADB
from a50_record import PhoneSession


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    private = Path(".deploy/a50")
    config = json.loads((private / "mirror-tools.json").read_text())
    executable = Path(config["executable"])
    if not executable.is_file():
        raise RuntimeError("Prepare the verified portable client first")
    # Recheck every portable file against the verified archive before running it.
    import hashlib
    import zipfile

    archive = Path("tmp/a50-mirror/scrcpy-win64-v4.1.zip")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != config["sha256"]:
        raise RuntimeError("Prepared archive changed; stop and inspect")
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if not member.is_dir() and (
                archive.parent / member.filename
            ).read_bytes() != package.read(member):
                raise RuntimeError("Prepared mirror file changed; stop and inspect")
    session = PhoneSession("mirror-open-for-user-login")
    adb = A50ADB(private / "adb.json")
    endpoint = adb.connect(timeout=40)
    for command, label in [
        (["shell", "input", "keyevent", "224"], "screen on [user login handoff]"),
        (
            ["shell", "am", "start", "-W", "-n", "com.aircon.family/.MainActivity"],
            "launch installed family release APK [user login handoff]",
        ),
    ]:
        result = adb.run("-s", endpoint, *command, timeout=30)
        session.log(
            "$ adb [verified A50] "
            + label
            + "\n"
            + (result.stdout + result.stderr).decode("utf-8", errors="replace")
        )
        if result.returncode:
            raise RuntimeError("Own app handoff failed")
    environment = dict(os.environ, ADB=str(Path(adb.adb).resolve()))
    # A visible GUI is intentional: the user requested direct Google sign-in.
    # Console output remains private; no recording or clipboard autosync is enabled.
    with (private / "mirror-output.log").open("wb") as log:
        process = subprocess.Popen(
            [
                str(executable),
                "--serial",
                endpoint,
                "--no-audio",
                "--no-clipboard-autosync",
                "--window-title",
                "A50 - Family Smart Home",
                "--max-size",
                "1440",
                "--window-height",
                "850",
            ],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    (private / "mirror-process.json").write_text(
        json.dumps({"pid": process.pid, "executable": str(executable), "opened_at": time.time()}),
        encoding="utf-8",
    )
    time.sleep(3)
    if process.poll() is not None:
        raise RuntimeError("Mirror client exited; inspect private mirror-output.log")
    session.log("MIRROR_PROCESS_RUNNING=TRUE USER_WINDOW=A50 - Family Smart Home")
    session.log("AUDIO=disabled VIDEO_RECORDING=none CLIPBOARD_AUTOSYNC=disabled")
    session.log("GOOGLE_ACCOUNT_PASSWORD_AND_CODES=USER_INPUT_ONLY NO_CREDENTIAL_CAPTURE")


if __name__ == "__main__":
    main()
