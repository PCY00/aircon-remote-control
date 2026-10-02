"""Use the existing, user-confirmed Pi SSH target and retain sanitized evidence."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/android"))
from a50_record import PhoneSession  # noqa: E402


class PiSession(PhoneSession):
    def command(self):
        # Same confirmed target/key as scripts/deploy.ps1; never auto-trust a host key.
        return [
            "ssh",
            "-i",
            str(Path.home() / ".ssh/airconpi"),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=10",
            "air@AC",
        ]
