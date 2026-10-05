"""Preview or install the locally verified A50 management APK on the paired phone."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shlex
from pathlib import Path

from a50_adb import A50ADB


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--configure-current-wifi", action="store_true")
    parser.add_argument("--config", type=Path, default=Path(".deploy/a50/adb.json"))
    parser.add_argument("--build", type=Path, default=Path("tmp/a50-manager-build"))
    args = parser.parse_args()
    build = json.loads((args.build / "build.json").read_text(encoding="utf-8"))
    apk = args.build / "a50-manager.apk"
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    if digest != build["apk_sha256"]:
        raise RuntimeError("APK differs from the locally verified build; no phone action taken.")
    print(f"LOCAL_VERIFIED_APK_SHA256={digest}")
    if not args.apply:
        print("PREVIEW_ONLY=NO_DEVICE_ACTION")
        print("UPDATE=own management APK; preserve installed app data")
        print("PERMISSIONS=own settings permission and battery optimization exception")
        if args.configure_current_wifi:
            print(
                "CONFIGURE=owner-approved current Wi-Fi/AP; private recovery capability; "
                "preserve accessibility services"
            )
        return 0

    client = A50ADB(args.config)
    # Bootstrap must already be connected; do not change settings while selecting an update target.
    client.config["ssh_recovery_enabled"] = False
    endpoint = client.connect(timeout=20)
    wifi = client.run("-s", endpoint, "shell", "cmd wifi status", timeout=15)
    if wifi.returncode:
        raise RuntimeError("Current Wi-Fi could not be measured; no update was installed.")
    text = wifi.stdout.decode("utf-8", errors="replace")
    network_match = re.search(r"\bSSID:\s*(.+?),\s*BSSID:", text)
    ap_match = re.search(r"BSSID:\s*([0-9a-fA-F:]{17})", text)
    if not network_match or not ap_match:
        raise RuntimeError("Current Wi-Fi/AP identity unavailable; no update was installed.")
    network = network_match.group(1).strip().strip('"')
    bssid = ap_match.group(1).lower()
    if (
        not network
        or network == "<unknown ssid>"
        or not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", bssid)
    ):
        raise RuntimeError("Current Wi-Fi/AP identity invalid; no update was installed.")
    token = client.config.get("manager_rpc_token", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token):
        token = secrets.token_urlsafe(32)
    directory = Path("docs/assets/terminal")
    number = max(int(path.name.split("-")[0]) for path in directory.glob("*.txt")) + 1
    transcript = directory / f"{number:02d}-a50-manager-verified-update.txt"
    transcript.write_text(
        "# Actual paired-device management update; private values removed\n\n", encoding="utf-8"
    )

    def run(command: str | tuple[str, ...], label: str) -> str:
        arguments = (
            ("-s", endpoint, "shell", command)
            if isinstance(command, str)
            else ("-s", endpoint, *command)
        )
        result = client.run(*arguments, timeout=90)
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
        safe = client.redact(output)
        for private in (network, bssid, token, str(Path.cwd()), str(Path.home())):
            safe = safe.replace(private, "[REDACTED]")
        safe = re.sub(r"/data/app/[^\s]+", "[REDACTED_INSTALLED_APK_PATH]", safe)
        with transcript.open("a", encoding="utf-8") as stream:
            stream.write(f"$ {label}\n{safe}EXIT_CODE={result.returncode}\n\n")
        print(f"{label}: EXIT_CODE={result.returncode}", flush=True)
        if result.returncode:
            raise RuntimeError("Phone step failed; later steps were not run.")
        return output

    run(
        ("push", str(apk.resolve()), "/data/local/tmp/a50-manager.apk"),
        "adb [verified A50] push [locally signed APK]",
    )
    run(
        "pm install -r /data/local/tmp/a50-manager.apk",
        "adb [verified A50] shell pm install -r /data/local/tmp/a50-manager.apk",
    )
    run(
        "pm grant com.aircon.a50manager android.permission.WRITE_SECURE_SETTINGS",
        "adb [verified A50] shell pm grant [own package] WRITE_SECURE_SETTINGS",
    )
    run(
        "dumpsys deviceidle whitelist +com.aircon.a50manager",
        "adb [verified A50] shell dumpsys deviceidle whitelist +com.aircon.a50manager",
    )
    if args.configure_current_wifi:
        command = (
            "am broadcast -a com.aircon.a50manager.CONFIGURE_TRUSTED_WIFI "
            "-n com.aircon.a50manager/.ConfigurationReceiver --es network "
            + shlex.quote(network)
            + " --es bssid "
            + shlex.quote(bssid)
            + " --es token "
            + shlex.quote(token)
        )
        output = run(
            command,
            "adb [verified A50] shell am broadcast "
            "[protected configuration; owner-approved Wi-Fi/AP and private capability]",
        )
        if "Broadcast completed: result=1" not in output:
            raise RuntimeError("Phone rejected management configuration.")
        current = run(
            "settings get secure enabled_accessibility_services",
            "adb [verified A50] shell settings get secure enabled_accessibility_services",
        )
        services = [] if current.strip() in ("", "null") else current.strip().split(":")
        own = "com.aircon.a50manager/com.aircon.a50manager.TrustedWifiApproval"
        if own not in services:
            services.append(own)
        run(
            "settings put secure enabled_accessibility_services " + shlex.quote(":".join(services)),
            "adb [verified A50] shell settings put secure enabled_accessibility_services "
            "[preserve existing, add own helper]",
        )
        run(
            "settings put secure accessibility_enabled 1",
            "adb [verified A50] shell settings put secure accessibility_enabled 1",
        )
        client.config["manager_rpc_token"] = token
        client.config["ssh_recovery_enabled"] = True
        args.config.write_text(json.dumps(client.config, indent=2) + "\n", encoding="utf-8")
    run(
        "am start -n com.aircon.a50manager/.MainActivity",
        "adb [verified A50] shell am start [own management UI]",
    )
    run(
        "am broadcast -a com.aircon.a50manager.STATUS -n com.aircon.a50manager/.StatusReceiver",
        "adb [verified A50] shell am broadcast [own read-only live status]",
    )
    remote = run(
        "pm path com.aircon.a50manager", "adb [verified A50] shell pm path com.aircon.a50manager"
    ).strip()
    path = remote.removeprefix("package:")
    if not path.startswith("/data/app/") or "\n" in path:
        raise RuntimeError("Unexpected installed APK path; no additional device command run.")
    observed = run(
        "sha256sum " + shlex.quote(path), "adb [verified A50] shell sha256sum [installed own APK]"
    ).split()[0]
    if observed != digest:
        raise RuntimeError("Installed APK checksum differs from the verified local build.")
    with transcript.open("a", encoding="utf-8") as stream:
        stream.write("LOCAL_DEVICE_APK_SHA256_MATCH=YES\n")
    print("LOCAL_DEVICE_APK_SHA256_MATCH=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
