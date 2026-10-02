"""Preview, reversibly disable, or restore reviewed consumer apps on the paired A50."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from a50_adb import A50ADB

APPS = {
    "com.google.android.youtube": "YouTube",
    "com.google.android.videos": "Google TV",
    "com.google.android.apps.photos": "Google Photos",
    "com.google.android.apps.docs": "Google Drive",
    "com.google.android.gm": "Gmail",
    "com.google.android.apps.maps": "Google Maps",
    "com.google.android.apps.tachyon": "Google Meet/Duo",
    "com.google.android.projection.gearhead": "Android Auto",
    "com.google.ar.core": "Google Play Services for AR",
    "com.samsung.android.game.gamehome": "Game Launcher",
}
PROTECTED = {
    "com.android.systemui", "com.android.settings", "com.sec.android.app.launcher",
    "com.samsung.android.honeyboard", "com.android.providers.settings",
    "com.android.providers.media", "com.android.providers.media.module",
    "com.android.providers.downloads", "com.android.externalstorage",
    "com.google.android.documentsui", "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller", "com.google.android.gms",
    "com.google.android.gsf", "com.android.vending", "com.google.android.webview",
    "com.android.chrome", "com.sec.android.app.sbrowser", "com.sec.android.app.myfiles",
    "com.sec.android.app.camera", "com.sec.android.gallery3d", "com.android.phone",
    "com.samsung.android.networkstack", "com.google.android.networkstack",
    "com.android.bluetooth", "com.termux", "com.termux.boot", "com.aircon.a50manager",
}


def active_package_state(
    output: str, package: str, *, verified_singleton_uid: bool = False
) -> dict:
    # Read the active Packages block, not the archived original of an updated system app.
    output = output.replace("\r", "")
    active = output.split("\nPackages:", 1)[-1].split("\nHidden system packages:", 1)[0]
    block = re.search(
        r"^  Package\s*\[" + re.escape(package) + r"\].*?(?=^  Package\s*\[|\Z)",
        active, re.MULTILINE | re.DOTALL,
    )
    if not block:
        raise RuntimeError("Active package metadata unavailable; no app change allowed.")
    value = block.group(0)
    user = re.search(r"^\s+User 0:.*\binstalled=(true|false).*\benabled=(\d+)", value, re.M)
    flags = re.search(r"\bpkgFlags=\[([^\]]*)\]", value)
    inode = re.search(r"\bceDataInode=(\d+)", value)
    if not user or not flags:
        raise RuntimeError("Package state incomplete; no app change allowed.")
    shared = re.search(r"sharedUser=SharedUserSetting\{\S+\s+(\S+)/(\d+)\}", value)
    safe_self_shared = shared and shared.group(1) == package and verified_singleton_uid
    if "PERSISTENT" in flags.group(1).split() or ("sharedUser=" in value and not safe_self_shared):
        raise RuntimeError("Persistent/shared-UID package rejected.")
    if re.search(r"^\s+(?:libraryNames|staticSharedLibName)=", value, re.M):
        raise RuntimeError("Provided shared-library package rejected.")
    return {"installed": user.group(1) == "true", "enabled": int(user.group(2)),
            "data_inode": inode.group(1) if inode else None}


def validate_baseline(baseline: dict) -> None:
    if baseline.get("schema") != 1 or set(baseline.get("apps", {})) != set(APPS):
        raise RuntimeError("Restore plan differs from the reviewed allowlist.")
    for package, state in baseline["apps"].items():
        if package in PROTECTED or not state.get("installed") or state.get("enabled") not in (0, 1):
            raise RuntimeError("Baseline must contain installed, initially enabled consumer apps.")


def restore_command(package: str, state: dict) -> str:
    if package not in APPS or package in PROTECTED or state.get("enabled") not in (0, 1):
        raise RuntimeError("Unreviewed restore request rejected.")
    verb = "default-state" if state["enabled"] == 0 else "enable"
    return f"pm {verb} --user 0 {package}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument(
        "--baseline", type=Path, default=Path(".deploy/a50/app-cleanup-20261002.json")
    )
    args = parser.parse_args()
    client = A50ADB(Path(".deploy/a50/adb.json"))
    endpoint = client.connect(timeout=40)
    directory = Path("docs/assets/terminal")
    number = max(int(p.name.split("-")[0]) for p in directory.glob("*.txt")) + 1
    label = "restore" if args.restore else ("apply" if args.apply else "preview")
    record = directory / f"{number:02d}-a50-consumer-app-cleanup-{label}.txt"
    record.write_text("# Actual reviewed consumer app cleanup; no uninstall or data clear\n\n",
                      encoding="utf-8")

    def log(value: str) -> None:
        safe = client.redact(value)
        safe = re.sub(r"ceDataInode=\d+", "ceDataInode=[REDACTED]", safe)
        with record.open("a", encoding="utf-8") as stream:
            stream.write(safe + "\n")
        print(safe, flush=True)

    def shell(command: str, visible: bool = True) -> str:
        response = client.run("-s", endpoint, "shell", command, timeout=25)
        text = (response.stdout + response.stderr).decode("utf-8", errors="replace")
        if visible:
            log("$ adb [verified A50] shell " + command + "\n" + text
                + "EXIT_CODE=" + str(response.returncode))
        if response.returncode:
            raise RuntimeError("Package operation rejected; see actual transcript.")
        return text

    def cores() -> None:
        enabled = {line.removeprefix("package:").strip()
                   for line in shell("pm list packages -e --user 0", False).splitlines() if line}
        missing = PROTECTED - enabled
        log("PROTECTED_ENABLED_COUNT=" + str(len(PROTECTED) - len(missing))
            + "/" + str(len(PROTECTED)))
        if missing:
            raise RuntimeError("Protected app not enabled; stop cleanup and inspect.")

    def ssh_check() -> None:
        response = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("a50_ssh.py")), "echo SSH_CLEANUP_OK"],
            capture_output=True, timeout=20,
        )
        log("$ a50_ssh.py 'echo SSH_CLEANUP_OK'\n" + client.redact(
            (response.stdout + response.stderr).decode("utf-8", errors="replace"))
            + "EXIT_CODE=" + str(response.returncode))
        if response.returncode or b"SSH_CLEANUP_OK" not in response.stdout:
            raise RuntimeError("Independent SSH fallback is unavailable; stop cleanup.")

    cores()
    ssh_check()
    uid_packages = re.findall(
        r"package:(\S+) uid:(\d+)", shell("pm list packages -U --user 0", False)
    )
    singletons = set()
    for package in APPS:
        ids = {uid for name, uid in uid_packages if name == package}
        if len(ids) == 1:
            own_uid = next(iter(ids))
            if {name for name, uid in uid_packages if uid == own_uid} == {package}:
                singletons.add(package)
        log("UID_MEMBERSHIP=" + package + " OWN_PACKAGE_ONLY=" + str(package in singletons))

    def app_state(package: str) -> dict:
        return active_package_state(shell("dumpsys package " + package, False), package,
                                    verified_singleton_uid=package in singletons)

    current = {package: app_state(package) for package in APPS}
    if args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    else:
        if args.restore:
            raise RuntimeError("Recorded baseline required for restore.")
        baseline = {"schema": 1, "apps": current}
    validate_baseline(baseline)
    for package, original in baseline["apps"].items():
        state = current[package]
        if not state["installed"] or state["enabled"] not in (original["enabled"], 3):
            raise RuntimeError("Unexpected app state; preserve and inspect before modification.")
        log(APPS[package] + " | " + package + " | current_enabled=" + str(state["enabled"])
            + " | original_enabled=" + str(original["enabled"]))
    if not args.apply:
        log("PREVIEW_ONLY=NO_DEVICE_MUTATION")
        return 0
    if not args.baseline.exists():
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    changed = []
    try:
        for package, original in baseline["apps"].items():
            expected = original["enabled"] if args.restore else 3
            if current[package]["enabled"] == expected:
                continue
            command = restore_command(package, original) if args.restore else (
                "pm disable-user --user 0 " + package
            )
            changed.append(package)
            shell(command)
            observed = app_state(package)
            if (not observed["installed"] or observed["enabled"] != expected
                    or observed["data_inode"] != current[package]["data_inode"]):
                raise RuntimeError("App state/data preservation check failed.")
            log("VERIFIED=" + package + " enabled=" + str(expected)
                + " installed=true DATA_INODE_UNCHANGED")
            cores()
        ssh_check()
        verified = client.verify(endpoint)
        log("PAIRED_ADB_FINAL_VERIFIED=" + str(verified))
        if not verified:
            raise RuntimeError("Final paired ADB check failed.")
        shell("am broadcast -a com.aircon.a50manager.STATUS "
              "-n com.aircon.a50manager/.StatusReceiver")
        log("CONSUMER_APP_" + label.upper() + "=PASS")
    except Exception:
        if not args.restore:
            log("CLEANUP_FAILED=ROLL_BACK_ONLY_APPS_CHANGED_IN_THIS_RUN")
            for package in reversed(changed):
                shell(restore_command(package, baseline["apps"][package]))
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
