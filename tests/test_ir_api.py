import subprocess
import sys
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from app.ir.backend import IrCtlReceiver
from app.ir.mock import MockReceiver
from app.main import create_app
from app.settings import Settings
from tests.ir_samples import make_capture


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8001,
        log_level="INFO",
        data_dir=data_dir,
        ir_ctl_path="ir-ctl",
        ir_receiver_device=Path("/dev/lirc0"),
        ir_capture_timeout_seconds=1,
    )


def wait_for_terminal(client: TestClient, capture_id: str) -> dict[str, object]:
    deadline = monotonic() + 2
    while monotonic() < deadline:
        response = client.get(f"/api/v1/ir/captures/{capture_id}")
        payload = response.json()
        if payload["status"] != "capturing":
            return payload
        sleep(0.01)
    raise AssertionError("capture did not finish")


def test_capture_api_analyzes_and_persists_packet(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver([make_capture()]))

    with TestClient(app) as client:
        status_response = client.get("/api/v1/ir/receiver")
        assert status_response.status_code == 200
        assert status_response.json()["backend"] == "mock"

        start_response = client.post(
            "/api/v1/ir/captures",
            json={"name": "cool-18-high", "profile_id": "carrier-16214-15597"},
        )
        assert start_response.status_code == 202
        capture_id = start_response.json()["id"]

        capture = wait_for_terminal(client, capture_id)
        assert capture["status"] == "completed"
        assert capture["analysis"]["first_frame"]["payload_hex"] == "b2 4d bf 40 20 df"
        assert capture["analysis"]["profile"]["validation"] == "matched"
        assert set(capture["files"]) == {"metadata", "compact", "irctl"}

        capture_dir = tmp_path / "captures"
        assert (capture_dir / f"{capture_id}.json").is_file()
        assert (capture_dir / f"{capture_id}.compact").is_file()
        assert (capture_dir / f"{capture_id}.ir").is_file()

        list_response = client.get("/api/v1/ir/captures")
        assert [item["id"] for item in list_response.json()["items"]] == [capture_id]

        delete_response = client.delete(f"/api/v1/ir/captures/{capture_id}")
        assert delete_response.status_code == 204
        assert not list(capture_dir.iterdir())


def test_only_one_capture_can_use_the_receiver(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver(wait_forever=True))

    with TestClient(app) as client:
        first = client.post("/api/v1/ir/captures", json={"name": "first"})
        assert first.status_code == 202

        second = client.post("/api/v1/ir/captures", json={"name": "second"})
        assert second.status_code == 409

        capture_id = first.json()["id"]
        cancelled = client.post(f"/api/v1/ir/captures/{capture_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


def test_rejects_unknown_remote_profile(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver([make_capture()]))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ir/captures",
            json={"name": "unknown", "profile_id": "no-such-remote"},
        )

    assert response.status_code == 422


def test_unparsable_capture_releases_receiver(tmp_path: Path) -> None:
    # ir-ctl prints "# overflow" when the kernel reports LIRC_MODE2_OVERFLOW.
    receiver = MockReceiver(["+4403 -4277 +650 -1501 # overflow", make_capture()])
    app = create_app(make_settings(tmp_path), receiver)

    with TestClient(app) as client:
        first = client.post("/api/v1/ir/captures", json={"name": "noisy"})
        failed = wait_for_terminal(client, first.json()["id"])
        second = client.post("/api/v1/ir/captures", json={"name": "retry"})
        assert second.status_code == 202
        retried = wait_for_terminal(client, second.json()["id"])

    assert failed["status"] == "failed"
    assert "non-integer" in failed["error"]
    assert failed["files"] == {"metadata": f"{failed['id']}.json"}
    assert (tmp_path / "captures" / f"{failed['id']}.json").is_file()
    assert retried["status"] == "completed"


def test_capture_rejects_blank_name(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver([make_capture()]))

    with TestClient(app) as client:
        response = client.post("/api/v1/ir/captures", json={"name": "   "})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("features", "available"),
    [
        ("Receive features /dev/lirc0:\n - Device cannot receive\n"
         "Send features /dev/lirc0:\n - Device can send raw IR\n", False),
        ("Receive features /dev/lirc1:\n - Device can receive raw IR\n"
         "Send features /dev/lirc1:\n - Device cannot send\n", True),
    ],
)
def test_receiver_status_requires_receive_feature(
    tmp_path: Path, features: str, available: bool
) -> None:
    device = tmp_path / "lirc"
    device.touch()
    calls: list[list[str]] = []

    def runner(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, features, "")

    status = IrCtlReceiver(sys.executable, device, runner=runner).status()

    assert status.available is available
    expected_detail = "ready" if available else "Device cannot receive"
    assert expected_detail in status.details
    assert calls == [[sys.executable, f"--device={device}", "--features"]]
