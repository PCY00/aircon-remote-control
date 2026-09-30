from pathlib import Path
from time import monotonic, sleep

from fastapi.testclient import TestClient

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
