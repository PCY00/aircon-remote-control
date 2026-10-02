"""Prepare the official portable scrcpy client with its published SHA-256."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

from a50_record import PhoneSession

VERSION = "4.1"
SHA256 = "5b12172b3264b2889f4583ee64752ce832e29bc8b1089dca81093459697165db"
URL = "https://github.com/Genymobile/scrcpy/releases/download/v4.1/scrcpy-win64-v4.1.zip"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    record = PhoneSession("mirror-tools-prepare")
    root = Path("tmp/a50-mirror")
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "scrcpy-win64-v4.1.zip"
    record.log("$ download official Genymobile/scrcpy v4.1 win64 archive; verify published SHA-256")
    if not archive.exists():
        with urllib.request.urlopen(URL, timeout=45) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError("Official archive checksum did not match; do not extract or run.")
    record.log("OFFICIAL_ARCHIVE_SHA256=PASS BYTES=" + str(archive.stat().st_size))
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (root / member.filename).resolve()
            if not target.is_relative_to(root.resolve()):
                raise RuntimeError("Unsafe archive path")
            if (
                not member.is_dir()
                and target.exists()
                and target.read_bytes() != package.read(member)
            ):
                raise RuntimeError("Existing portable client changed; preserve and inspect.")
        package.extractall(root)
    executable = root / "scrcpy-win64-v4.1/scrcpy.exe"
    if not executable.is_file():
        raise RuntimeError("Portable mirror executable missing")
    private = Path(".deploy/a50/mirror-tools.json")
    private.write_text(
        json.dumps({"version": VERSION, "sha256": SHA256, "executable": str(executable.resolve())}),
        encoding="utf-8",
    )
    record.log("PORTABLE_MIRROR_TOOLS=PREPARED WINDOWS_INSTALL=none DEVICE_CHANGES=none")


if __name__ == "__main__":
    main()
