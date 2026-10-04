"""Host-only checks for the Zigbee IR wire format; no board is accessed."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
ZIGBEE_MAIN = ROOT / "firmware/esp32-h2-zigbee-ir-node/main"
USB_MAIN = ROOT / "firmware/esp32-h2-ir-node/main"


def test_carrier_profile_matches_validated_usb_firmware() -> None:
    def definitions(source: str) -> dict[str, str]:
        return dict(re.findall(r"^#define (\w+)\s+(.+)$", source, flags=re.MULTILINE))

    usb = (USB_MAIN / "carrier_profile.h").read_text(encoding="utf-8")
    zigbee = (ZIGBEE_MAIN / "carrier_profile.h").read_text(encoding="utf-8")
    usb_defs = definitions(usb)
    zigbee_defs = definitions(zigbee)
    for key in ("IR_CARRIER_HZ", "LEADER_PULSE_US", "LEADER_SPACE_US",
                "BIT_PULSE_US", "ZERO_SPACE_US", "ONE_SPACE_US",
                "INTER_FRAME_SPACE_US", "FRAME_BYTE_COUNT", "FRAME_REPEAT_COUNT"):
        assert zigbee_defs[key] == usb_defs[key]
    usb_off = re.search(r"POWER_OFF\[FRAME_BYTE_COUNT\] = \{([^}]+)\}", usb).group(1)
    zigbee_off = re.search(r"POWER_OFF\[FRAME_BYTE_COUNT\] = \{([^}]+)\}", zigbee).group(1)
    assert zigbee_off == usb_off


def test_zigbee_wire_parser_and_carrier_frames(tmp_path: Path) -> None:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if not compiler and os.name == "nt":
        candidate = Path("C:/msys64/ucrt64/bin/gcc.exe")
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        pytest.skip("C compiler is required")

    shutil.copyfile(ZIGBEE_MAIN / "ir_protocol.h", tmp_path / "ir_protocol.h")
    shutil.copyfile(ZIGBEE_MAIN / "carrier_profile.h", tmp_path / "carrier_profile.h")
    shutil.copyfile(ROOT / "tests/firmware/h2_zigbee_protocol_test.c", tmp_path / "protocol_test.c")
    executable = tmp_path / ("protocol_test.exe" if os.name == "nt" else "protocol_test")
    environment = os.environ.copy()
    environment["PATH"] = str(Path(compiler).parent) + os.pathsep + environment.get("PATH", "")
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "protocol_test.c", "-o", str(executable)], cwd=tmp_path,
                   check=True, capture_output=True, text=True, env=environment)
    result = subprocess.run([str(executable)], check=True, capture_output=True,
                            text=True, timeout=5, env=environment)
    assert "all checks passed" in result.stdout

    profile = json.loads((ROOT / "device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json")
                         .read_text(encoding="utf-8"))
    fixed_commands = {
        1: "power_off", 3: "mode_auto", 4: "mode_dry", 5: "mode_fan_only",
        6: "economy", 7: "turbo", 8: "led_toggle", 9: "airflow_fix",
        10: "swing_toggle",
    }
    fan_names = ("auto", "low", "medium", "high")
    encoder = profile["encoders"]["cool_state"]
    seen: set[tuple[int, int, int]] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("FRAME "):
            continue
        _, command_text, temperature_text, fan_text, count_text, *frames = line.split()
        command, temperature, fan, count = map(
            int, (command_text, temperature_text, fan_text, count_text)
        )
        seen.add((command, temperature, fan))
        assert len(frames) == count
        if command == 2:
            offset = temperature - encoder["temperature_min_c"]
            temperature_byte = (offset ^ (offset >> 1)) << 4
            frame = (
                "".join(encoder["prefix"])
                + "".join(encoder["fan_bytes"][fan_names[fan]])
                + f"{temperature_byte:02x}{temperature_byte ^ 0xff:02x}"
            )
            expected = [frame] * encoder["repeat_count"]
        else:
            assert temperature == fan == 0
            source_frames = profile["commands"][fixed_commands[command]]["frames_hex"]
            expected = ["".join(frame) for frame in source_frames]
        assert frames == expected
    assert seen == {(command, 0, 0) for command in fixed_commands} | {
        (2, temperature, fan) for temperature in range(17, 31) for fan in range(4)
    }
