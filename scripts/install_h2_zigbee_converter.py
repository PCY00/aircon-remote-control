"""Install the reviewed H2 converter into the Pi's mutable Zigbee2MQTT data.

Preview is the default. Applying requires the configuration checksum observed
during preview, so an intervening runtime edit cannot be silently overwritten.
The Zigbee2MQTT container is deliberately not restarted by this script.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import tempfile
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def enable_external_js(config: bytes) -> tuple[bytes, str]:
    text = config.decode("utf-8")
    if "\r" in text:
        raise ValueError("Unexpected configuration line endings; no change made")
    lines = text.splitlines(keepends=True)
    advanced = [i for i, line in enumerate(lines) if line.rstrip("\n") == "advanced:"]
    if len(advanced) != 1:
        raise ValueError("Expected exactly one top-level advanced section")

    start = advanced[0] + 1
    end = next(
        (
            i
            for i in range(start, len(lines))
            if lines[i].strip() and not lines[i].startswith((" ", "\t", "#"))
        ),
        len(lines),
    )
    settings = [
        i for i in range(start, end) if re.match(r"^  enable_external_js:", lines[i])
    ]
    if len(settings) > 1:
        raise ValueError("Duplicate enable_external_js settings")
    if settings:
        old = lines[settings[0]].rstrip("\n")
        if old == "  enable_external_js: true":
            return config, "already-enabled"
        if old != "  enable_external_js: false":
            raise ValueError("Unsupported enable_external_js syntax")
        lines[settings[0]] = "  enable_external_js: true\n"
        return "".join(lines).encode("utf-8"), "false-to-true"

    lines.insert(start, "  enable_external_js: true\n")
    return "".join(lines).encode("utf-8"), "added"


def atomic_private_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-config-sha256")
    parser.add_argument("--expected-converter-sha256")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / "deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs"
    runtime = root / "runtime/zigbee/zigbee2mqtt"
    config_path = runtime / "configuration.yaml"
    target_dir = runtime / "external_converters"
    target = target_dir / source.name
    backup_dir = root / "runtime/zigbee/backups"

    if not source.is_file() or not config_path.is_file() or not backup_dir.is_dir():
        parser.error("Converter source, runtime configuration, or backup directory missing")
    if (
        source.is_symlink()
        or config_path.is_symlink()
        or target_dir.is_symlink()
        or target.is_symlink()
    ):
        parser.error("Symlink at a runtime target; refusing to modify it")
    if target_dir.exists() and not target_dir.is_dir():
        parser.error("Converter target path is not a directory")

    source_bytes = source.read_bytes()
    config_bytes = config_path.read_bytes()
    target_bytes = target.read_bytes() if target.exists() else None
    expected_config = sha256(config_bytes)
    updated_config, change = enable_external_js(config_bytes)
    target_hash = sha256(target_bytes) if target_bytes is not None else None
    converter_action = (
        "install" if target_bytes is None else
        ("keep" if target_bytes == source_bytes else "replace")
    )

    print(f"CONFIG_SHA256={expected_config}")
    print(f"CONVERTER_SHA256={sha256(source_bytes)}")
    print(f"CURRENT_CONVERTER_SHA256={target_hash or 'missing'}")
    print(f"CONVERTER_ACTION={converter_action}")
    print(f"EXTERNAL_JS_ACTION={change}")
    print("RESTART_REQUIRED=aircon-zigbee2mqtt")
    if not args.apply:
        print("NO_REMOTE_CHANGES=preview-only")
        return

    if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_config_sha256 or ""):
        parser.error("--apply requires --expected-config-sha256 from preview")
    if args.expected_config_sha256.lower() != expected_config:
        parser.error("Runtime configuration changed after preview; no change made")
    if converter_action == "replace":
        if not re.fullmatch(r"[0-9a-fA-F]{64}", args.expected_converter_sha256 or ""):
            parser.error("Replacement requires --expected-converter-sha256 from preview")
        if args.expected_converter_sha256.lower() != target_hash:
            parser.error("Runtime converter changed after preview; no change made")

    backup_fd, config_backup_name = tempfile.mkstemp(
        prefix="configuration.pre-h2-external-js-", suffix=".yaml", dir=backup_dir
    )
    with os.fdopen(backup_fd, "wb") as stream:
        stream.write(config_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(config_backup_name, stat.S_IRUSR | stat.S_IWUSR)

    if not target_dir.exists():
        target_dir.mkdir(mode=0o700)
    if converter_action == "replace" and target_bytes is not None:
        backup_fd, converter_backup_name = tempfile.mkstemp(
            prefix="aircon-h2-ir.pre-update-", suffix=".mjs", dir=backup_dir
        )
        with os.fdopen(backup_fd, "wb") as stream:
            stream.write(target_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(converter_backup_name, stat.S_IRUSR | stat.S_IWUSR)
        print(f"PRIVATE_CONVERTER_BACKUP={converter_backup_name}")
    if converter_action != "keep":
        atomic_private_write(target, source_bytes)
    if updated_config != config_bytes:
        atomic_private_write(config_path, updated_config)

    print(f"PRIVATE_CONFIG_BACKUP={config_backup_name}")
    print(f"CONFIG_SHA256_AFTER={sha256(config_path.read_bytes())}")
    print(f"CONVERTER_SHA256_AFTER={sha256(target.read_bytes())}")
    print("INSTALL_STATUS=ready-for-zigbee2mqtt-restart")


if __name__ == "__main__":
    main()
