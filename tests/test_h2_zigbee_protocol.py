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
PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"
# Coolix temperature nibbles for 17..30 C. Plain Gray code differs at 27/28 C
# (0xF/0xE); 0xE is the fan-only (no temperature) code.
COOLIX_TEMPERATURE_CODES = (0x0, 0x1, 0x3, 0x2, 0x6, 0x7, 0x5, 0x4,
                            0xC, 0xD, 0x9, 0x8, 0xA, 0xB)
ECONOMY_FRAME = "b24de01f03fc"
FAN_NAMES = ("auto", "low", "medium", "high")


def compile_protocol_test(tmp_path: Path) -> subprocess.CompletedProcess:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if not compiler and os.name == "nt":
        candidate = Path("C:/msys64/ucrt64/bin/gcc.exe")
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        pytest.skip("C compiler is required")

    for header in ("ir_protocol.h", "carrier_profile.h", "command_policy.h",
                   "commissioning_retry.h"):
        shutil.copyfile(ZIGBEE_MAIN / header, tmp_path / header)
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
    return result


def firmware_frames(result: subprocess.CompletedProcess) -> dict[tuple[int, int, int], list[str]]:
    frames: dict[tuple[int, int, int], list[str]] = {}
    for line in result.stdout.splitlines():
        if not line.startswith("FRAME "):
            continue
        _, command_text, temperature_text, fan_text, count_text, *hex_frames = line.split()
        command, temperature, fan, count = map(
            int, (command_text, temperature_text, fan_text, count_text)
        )
        assert len(hex_frames) == count
        frames[(command, temperature, fan)] = hex_frames
    return frames


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
    result = compile_protocol_test(tmp_path)

    profile = json.loads((ROOT / "device_profiles/air_conditioner/Carrier/CS-A061GS/commands.json")
                         .read_text(encoding="utf-8"))
    fixed_commands = {
        1: "power_off", 3: "mode_auto", 4: "mode_dry", 5: "mode_fan_only",
        6: "economy", 7: "turbo", 8: "led_toggle", 9: "airflow_fix",
        10: "swing_toggle",
    }
    encoder = profile["encoders"]["cool_state"]
    frames_by_request = firmware_frames(result)
    for (command, temperature, fan), frames in frames_by_request.items():
        if command == 2:
            temperature_byte = COOLIX_TEMPERATURE_CODES[temperature - 17] << 4
            assert temperature_byte >> 4 != 0xE
            frame = (
                "".join(encoder["prefix"])
                + "".join(encoder["fan_bytes"][FAN_NAMES[fan]])
                + f"{temperature_byte:02x}{temperature_byte ^ 0xff:02x}"
            )
            expected = [frame] * encoder["repeat_count"]
        elif command == 6:
            # ECONOMY sends only the eco/sleep frame, once as captured; the Pi follows
            # with COOL_STATE for the current setpoint instead of the captured 17 C.
            assert temperature == fan == 0
            source_frames = profile["commands"][fixed_commands[command]]["frames_hex"]
            assert ["".join(frame) for frame in source_frames] == [ECONOMY_FRAME]
            expected = [ECONOMY_FRAME]
        else:
            assert temperature == fan == 0
            source_frames = profile["commands"][fixed_commands[command]]["frames_hex"]
            expected = ["".join(frame) for frame in source_frames]
        assert frames == expected
    assert set(frames_by_request) == {(command, 0, 0) for command in fixed_commands} | {
        (2, temperature, fan) for temperature in range(17, 31) for fan in range(4)
    }
    assert frames_by_request[(2, 27, 0)] == ["b24dbf40906f"] * 2
    assert frames_by_request[(2, 28, 0)] == ["b24dbf40807f"] * 2


def test_firmware_cool_state_matches_pi_resolver_byte_for_byte(tmp_path: Path) -> None:
    from app.devices.catalog import DeviceProfileCatalog
    from app.devices.commands import DeviceCommandResolver

    frames_by_request = firmware_frames(compile_protocol_test(tmp_path))
    resolver = DeviceCommandResolver(DeviceProfileCatalog(ROOT / "device_profiles"))
    for temperature in range(17, 31):
        for fan, fan_name in enumerate(FAN_NAMES):
            resolved = resolver.resolve(PROFILE_ID, {
                "action": "set_state", "power": True, "mode": "cool",
                "temperature_c": temperature, "fan": fan_name,
            })
            assert ["".join(frame) for frame in resolved["frames_hex"]] == (
                frames_by_request[(2, temperature, fan)]
            ), (temperature, fan_name)


def test_commissioning_failures_are_retried_without_ir() -> None:
    source = (ZIGBEE_MAIN / "main.c").read_text(encoding="utf-8")
    handler = source[source.index("static bool zigbee_signal_handler"):]
    handler = handler[:handler.index("\n}\n")]
    assert "reboot to retry" not in source
    assert "schedule_commissioning(EZB_BDB_MODE_INITIALIZATION);" in handler
    assert "schedule_commissioning(EZB_BDB_MODE_NETWORK_STEERING);" in handler
    assert handler.count("commissioning_next_delay_ms = COMMISSIONING_RETRY_MIN_MS;") == 4
    # Every start goes through start_commissioning, which retries when the
    # stack refuses to start (no BDB failure signal would follow).
    assert "ezb_bdb_start_top_level_commissioning" not in handler
    starter = source[source.index("static void start_commissioning"):]
    starter = starter[:starter.index("\n}\n")]
    assert "ezb_bdb_start_top_level_commissioning(mode)" in starter
    assert "schedule_commissioning(mode);" in starter
    assert "start_commissioning(EZB_BDB_MODE_NETWORK_STEERING);" in handler
    # Leave without rejoin (removed in Zigbee2MQTT) steers again with backoff;
    # leave with rejoin is left to the stack.
    leave = handler[handler.index("case EZB_ZDO_SIGNAL_LEAVE:"):]
    leave = leave[:leave.index("break;\n    }")]
    assert "EZB_ZDO_LEAVE_TYPE_REJOIN" in leave
    assert "schedule_commissioning(EZB_BDB_MODE_NETWORK_STEERING);" in leave
    retry = source[source.index("static void commissioning_retry"):]
    retry = retry[:retry.index("\n}\n")]
    assert "esp_zigbee_lock_acquire" in retry and "esp_zigbee_lock_release" in retry
    assert "start_commissioning(commissioning_mode);" in retry
    for body in (handler, retry, starter):
        assert "aircon_ir_send" not in body and "xQueueSend" not in body
    assert "esp_timer_create(" in source
    assert re.search(r"REQUIRES[^)]*\besp_timer\b",
                     (ZIGBEE_MAIN / "CMakeLists.txt").read_text(encoding="utf-8"))


def test_commands_are_coordinator_only_and_paced(tmp_path: Path) -> None:
    # The pure helpers are exercised by the compiled host test; this checks
    # that main.c actually wires them in and that the README documents them.
    result = compile_protocol_test(tmp_path)
    policy = dict(
        item.split("=")
        for line in result.stdout.splitlines() if line.startswith("POLICY ")
        for item in line.split()[1:]
    )
    assert policy == {"state_gap_ms": "2000", "feature_gap_ms": "500", "reject_log_ms": "60000"}

    source = (ZIGBEE_MAIN / "main.c").read_text(encoding="utf-8")
    # The mirrored SDK address modes are pinned at firmware build time.
    assert "_Static_assert(AIRCON_ADDR_MODE_SHORT == EZB_ADDR_MODE_SHORT" in source
    assert "_Static_assert(AIRCON_ADDR_MODE_EXT == EZB_ADDR_MODE_EXT" in source
    checker = source[source.index("static bool source_is_coordinator"):]
    checker = checker[:checker.index("\n}\n")]
    assert "ezb_address_short_by_extended(&source->u.extended_addr" in checker
    assert "return aircon_source_is_coordinator(mode, short_addr);" in checker
    handler = source[source.index("static ezb_zcl_status_t aircon_command_handler"):]
    handler = handler[:handler.index("\n}\n")]
    # Non-coordinator sources get NOT_AUTHORIZED before the payload is decoded
    # or anything is queued; accepted requests are still answered immediately.
    rejection = handler.index("if (!source_is_coordinator(&header->src_addr))")
    assert rejection < handler.index("aircon_decode_request(")
    assert rejection < handler.index("xQueueSend(")
    assert "send_default_error(header, EZB_ZCL_STATUS_NOT_AUTHORIZED)" in handler
    assert "log_rejected_source(header);" in handler
    assert "AIRCON_RESULT_ACCEPTED" in handler
    logger = source[source.index("static void log_rejected_source"):]
    logger = logger[:logger.index("\n}\n")]
    assert "aircon_reject_log_due(logged, last_log_ms, now_ms)" in logger
    worker = source[source.index("static void ir_worker"):]
    worker = worker[:worker.index("\n}\n")]
    # The worker waits out the pacing gap before every transmission and
    # restamps after it; results are sent exactly as before.
    assert worker.index("ir_pacing_delay_ms(") < worker.index("aircon_ir_send(&job.request)")
    assert "vTaskDelay(pdMS_TO_TICKS(wait_ms) + 1U);" in worker
    assert worker.index("aircon_ir_send(&job.request)") < worker.index("last_tx_ms = uptime_ms();")
    assert "send_result(&job.header, &job.request, status)" in worker
    # Wire protocol untouched: same command ids and request sizes as the converter.
    protocol = (ZIGBEE_MAIN / "ir_protocol.h").read_text(encoding="utf-8")
    for line in ("#define AIRCON_ZCL_SEND_COMMAND 0x00U", "#define AIRCON_ZCL_SEND_V2_COMMAND 0x02U",
                 "#define AIRCON_REQUEST_V1_SIZE 6U", "#define AIRCON_REQUEST_V2_SIZE 8U",
                 "#define AIRCON_RESULT_SIZE 7U"):
        assert line in protocol
    readme = (ZIGBEE_MAIN.parent / "README.md").read_text(encoding="utf-8")
    security = readme[readme.index("\n## Zigbee security\n"):]
    security = security[1:security.index("\n## ", 1)]
    for phrase in ("0x0000", "NOT_AUTHORIZED", "2 s", "0.5 s", "install code", "permit-join"):
        assert phrase in security, phrase


def test_capability_identifies_coolix_economy_retry_firmware() -> None:
    # Capability 2 marks the Coolix 27/28 C table, eco-only ECONOMY and
    # commissioning retry; deployed capability 1 firmware lacks them.
    source = (ZIGBEE_MAIN / "main.c").read_text(encoding="utf-8")
    assert re.search(r"^static uint8_t capability = 2;$", source, flags=re.MULTILINE)
    assert re.search(r"EZB_ZCL_ATTR_TYPE_UINT8,\s*EZB_ZCL_ATTR_ACCESS_READ, &capability\)",
                     source)
    converter = (ROOT / "deploy/zigbee/zigbee2mqtt/external_converters/aircon-h2-ir.mjs"
                 ).read_text(encoding="utf-8")
    assert "capability: {name: 'capability', ID: 0x0000, type: Zcl.DataType.UINT8}" in converter


def test_rmt_refill_isr_is_cache_safe() -> None:
    ir_tx = (ZIGBEE_MAIN / "ir_tx.c").read_text(encoding="utf-8")
    profile = (ZIGBEE_MAIN / "carrier_profile.h").read_text(encoding="utf-8")
    defaults = (ZIGBEE_MAIN.parent / "sdkconfig.defaults").read_text(encoding="utf-8")
    definitions = dict(re.findall(r"^#define (\w+)\s+(\d+)U$", profile, flags=re.MULTILINE))
    frame_symbols = 1 + int(definitions["FRAME_BYTE_COUNT"]) * 8 + 1
    command_symbols = frame_symbols * int(definitions["MAX_FRAME_COUNT"])
    requested = int(re.search(r"\.mem_block_symbols = (\d+)", ir_tx).group(1))
    # ESP32-H2 has no RMT DMA and 48-word channel blocks; longer commands are
    # refilled by the TX ISR, which must run while flash writes disable cache.
    hardware_symbols = -(-requested // 48) * 48
    if ".with_dma = false" in ir_tx and command_symbols > hardware_symbols:
        assert "CONFIG_RMT_TX_ISR_CACHE_SAFE=y" in defaults.splitlines()
        assert "#if !defined(CONFIG_RMT_TX_ISR_CACHE_SAFE)" in ir_tx
    assert command_symbols > hardware_symbols  # current design relies on refills
