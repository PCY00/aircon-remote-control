"""Execute the actual IR C encoder and failure paths with host-side IDF doubles.

The host test does not access GPIO, serial ports or an air conditioner.
It cannot establish the board's measured carrier frequency or appliance response.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.transport import render_ir_ctl_payload

ROOT = Path(__file__).parents[1]
PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"


@pytest.fixture(scope="module")
def h2_host_test(tmp_path_factory: pytest.TempPathFactory) -> Path:
    compiler = shutil.which("gcc") or shutil.which("clang")
    if not compiler and os.name == "nt":
        candidate = Path("C:/msys64/ucrt64/bin/gcc.exe")
        if candidate.is_file():
            compiler = str(candidate)
    if not compiler:
        pytest.skip("A host C compiler (gcc or clang) is required for H2 firmware tests")

    build_dir = tmp_path_factory.mktemp("h2-ir-host")
    stub_header = ROOT / "tests/firmware/h2_ir_test_stubs.h"
    for header in (
        "driver/gpio.h",
        "driver/rmt_tx.h",
        "esp_check.h",
        "esp_err.h",
        "esp_log.h",
        "esp_system.h",
        "freertos/FreeRTOS.h",
        "freertos/task.h",
    ):
        destination = build_dir / header
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text('#include "h2_ir_test_stubs.h"\n', encoding="ascii")
    executable = build_dir / ("h2-ir-test.exe" if os.name == "nt" else "h2-ir-test")
    env = os.environ.copy()
    env["PATH"] = str(Path(compiler).parent) + os.pathsep + env.get("PATH", "")
    subprocess.run(
        [
            compiler,
            "-std=gnu11",
            "-O0",
            "-I", str(build_dir),
            "-I", str(stub_header.parent),
            "-I", str(ROOT / "firmware/esp32-h2-ir-node/main"),
            str(ROOT / "tests/firmware/h2_ir_host_test.c"),
            "-o", str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return executable


def run_firmware(executable: Path, command: str) -> dict:
    result = subprocess.run(
        [str(executable), command], check=True, capture_output=True, text=True, timeout=10
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("command", "device_request"),
    [
        ("off", {"action": "set_state", "power": False}),
        ("on", {"action": "set_state", "power": True, "mode": "cool",
                "temperature_c": 17, "fan": "high"}),
    ],
)
def test_h2_waveform_matches_pi_profile(
    h2_host_test: Path, command: str, device_request: dict
) -> None:
    resolved = DeviceCommandResolver(DeviceProfileCatalog(ROOT / "device_profiles")).resolve(
        PROFILE_ID, device_request
    )
    pi_payload, _, _ = render_ir_ctl_payload(resolved)
    expected = [int(line.split()[1]) for line in pi_payload.splitlines()[1:]]
    actual = run_firmware(h2_host_test, command)
    durations = [duration for symbol in actual["symbols"] for duration in symbol]
    # RMT requires a trailing space slot; the encoder adds one idle microsecond.
    assert durations[-1] == 1
    assert durations[:-1] == expected
    assert actual["carrier_hz"] == resolved["carrier_hz"]
    assert actual["result"] == 0
    assert actual["transmits"] == 1


@pytest.mark.parametrize(("command", "bursts", "duration_ms"), [
    ("camera2", 10, 2000),
    ("camera5", 25, 5000),
])
def test_h2_camera_duration_and_short_bursts(
    h2_host_test: Path, command: str, bursts: int, duration_ms: int
) -> None:
    actual = run_firmware(h2_host_test, command)
    assert actual["result"] == 0
    assert actual["transmits"] == bursts
    assert actual["ticks"] == duration_ms
    assert actual["symbols"] == [[20000, 20000]]


@pytest.mark.parametrize("command", ["timeout", "submit_error", "stop_error"])
def test_h2_tx_failure_blocks_new_commands_and_preserves_payload(
    h2_host_test: Path, command: str
) -> None:
    actual = run_firmware(h2_host_test, command)
    assert actual["result"] != 0
    assert actual["transmits"] == 1
    assert actual["stops"] == 1
