import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.transport import (
    InvalidTransmissionError,
    IrCtlTransport,
    TransportExecutionError,
    render_ir_ctl_payload,
)
from app.ir.mock import MockReceiver
from app.main import create_app
from app.settings import Settings

PROFILE_ROOT = Path(__file__).parents[1] / "device_profiles"
PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"
SIGNAL_ROOT = Path(__file__).parents[1] / "signals" / "remote-16214-15597" / "raw"


def sample_command(*, frames: list[list[str]] | None = None) -> dict[str, object]:
    return {
        "command_id": "test_command",
        "carrier_hz": 38_000,
        "bit_order": "msb_first_observed",
        "timing_us": {
            "leader_pulse": 4_350,
            "leader_space": 4_350,
            "bit_pulse": 560,
            "zero_space": 520,
            "one_space": 1_610,
            "inter_frame_space": 5_150,
        },
        "frames_hex": frames or [["80"]],
    }


class FakeIrCtlRunner:
    def __init__(self, *, send_returncode: int = 0) -> None:
        self.send_returncode = send_returncode
        self.calls: list[list[str]] = []
        self.payload: str | None = None

    def __call__(self, args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if "--features" in args:
            return subprocess.CompletedProcess(
                args,
                0,
                "Send features /dev/lirc-test:\n - Device can send raw IR\n",
                "",
            )

        send_argument = next(argument for argument in args if argument.startswith("--send="))
        self.payload = Path(send_argument.removeprefix("--send=")).read_text(encoding="ascii")
        return subprocess.CompletedProcess(
            args,
            self.send_returncode,
            "",
            "simulated send failure" if self.send_returncode else "",
        )


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8001,
        log_level="INFO",
        data_dir=data_dir,
        device_profiles_dir=PROFILE_ROOT,
        ir_ctl_path="ir-ctl",
        ir_receiver_device=Path("/dev/lirc0"),
        ir_capture_timeout_seconds=1,
        max_upload_bytes=1024,
    )


def test_render_ir_ctl_payload_uses_msb_bits_and_trailing_pulse() -> None:
    payload, duration_us, frame_count = render_ir_ctl_payload(sample_command())
    lines = payload.splitlines()

    assert lines[:6] == [
        "carrier 38000",
        "pulse 4350",
        "space 4350",
        "pulse 560",
        "space 1610",
        "pulse 560",
    ]
    assert lines[-1] == "pulse 560"
    assert len(lines) == 20
    assert duration_us == 18_990
    assert frame_count == 1


def test_render_ir_ctl_payload_inserts_only_one_inter_frame_gap() -> None:
    payload, duration_us, frame_count = render_ir_ctl_payload(
        sample_command(frames=[["80"], ["80"]])
    )

    assert payload.splitlines().count("space 5150") == 1
    assert payload.splitlines()[-1] == "pulse 560"
    assert duration_us == 43_130
    assert frame_count == 2


def test_render_ir_ctl_payload_rejects_unsupported_bit_order() -> None:
    command = sample_command()
    command["bit_order"] = "lsb_first"

    with pytest.raises(InvalidTransmissionError, match="MSB-first"):
        render_ir_ctl_payload(command)


def test_power_off_rendered_shape_matches_recorded_raw_capture() -> None:
    command = DeviceCommandResolver(DeviceProfileCatalog(PROFILE_ROOT)).resolve(
        PROFILE_ID,
        {"action": "set_state", "power": False},
    )
    generated, _, _ = render_ir_ctl_payload(command)
    recorded = (SIGNAL_ROOT / "power-off-from-cool-17-high-01.ir").read_text(
        encoding="utf-8"
    )

    def shape(payload: str) -> list[str]:
        result: list[str] = []
        for line in payload.splitlines():
            if not line.startswith(("pulse ", "space ")):
                continue
            kind, raw_duration = line.split()
            duration = int(raw_duration)
            if kind == "pulse":
                result.append("leader-pulse" if duration > 3_000 else "bit-pulse")
            elif duration > 3_000:
                result.append("long-gap")
            elif duration > 1_000:
                result.append("one-space")
            else:
                result.append("zero-space")
        return result

    assert shape(generated) == shape(recorded)


def test_ir_ctl_transport_sends_temporary_payload_and_records_history(tmp_path: Path) -> None:
    command_path = tmp_path / "ir-ctl"
    command_path.touch()
    device_path = tmp_path / "lirc-test"
    device_path.touch()
    runner = FakeIrCtlRunner()
    transport = IrCtlTransport(str(command_path), device_path, 2, runner)

    assert transport.status()["hardware_output"] is True
    transmission = transport.send(
        device_id="device-1",
        profile_id=PROFILE_ID,
        command=sample_command(),
    )

    assert runner.payload is not None
    assert runner.payload.startswith("carrier 38000\npulse 4350\n")
    assert transmission["status"] == "sent"
    assert transmission["hardware_output"] is True
    assert transmission["appliance_state_confirmed"] is False
    assert transport.list() == [transmission]


def test_ir_ctl_transport_does_not_record_failed_send(tmp_path: Path) -> None:
    command_path = tmp_path / "ir-ctl"
    command_path.touch()
    device_path = tmp_path / "lirc-test"
    device_path.touch()
    runner = FakeIrCtlRunner(send_returncode=1)
    transport = IrCtlTransport(str(command_path), device_path, 2, runner)

    with pytest.raises(TransportExecutionError, match="simulated send failure"):
        transport.send(
            device_id="device-1",
            profile_id=PROFILE_ID,
            command=sample_command(),
        )

    assert transport.list() == []


def test_device_api_reports_real_transport_result(tmp_path: Path) -> None:
    command_path = tmp_path / "ir-ctl"
    command_path.touch()
    device_path = tmp_path / "lirc-test"
    device_path.touch()
    transport = IrCtlTransport(str(command_path), device_path, 2, FakeIrCtlRunner())
    app = create_app(make_settings(tmp_path), MockReceiver(), transport)

    with TestClient(app) as client:
        registered = client.post(
            "/api/v1/devices",
            json={"name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID},
        )
        device_id = registered.json()["id"]
        response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "set_state", "power": False},
        )
        history = client.get("/api/v1/ir/transmissions")

    assert response.status_code == 200
    transmission = response.json()["transmission"]
    assert transmission["status"] == "sent"
    assert transmission["frame_count"] == 2
    assert transmission["hardware_output"] is True
    assert history.json()["items"] == [transmission]
