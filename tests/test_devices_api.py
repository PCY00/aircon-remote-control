from pathlib import Path

from fastapi.testclient import TestClient

from app.ir.mock import MockReceiver
from app.main import create_app
from app.settings import Settings

PROFILE_ROOT = Path(__file__).parents[1] / "device_profiles"
PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"


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


def register_air_conditioner(client: TestClient) -> str:
    response = client.post(
        "/api/v1/devices",
        json={
            "name": "거실 에어컨",
            "room": "거실",
            "profile_id": PROFILE_ID,
            "icon": "snowflake",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_catalog_exposes_carrier_profile(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        response = client.get("/api/v1/device-profiles")
        detail = client.get(f"/api/v1/device-profiles/{PROFILE_ID}")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [PROFILE_ID]
    assert detail.status_code == 200
    assert detail.json()["capabilities"]["temperature_c"] == {
        "minimum": 17,
        "maximum": 30,
        "step": 1,
    }
    assert "power_off" in detail.json()["command_ids"]
    assert detail.json()["encoders"] == ["cool_state"]


def test_register_and_resolve_cool_state_to_mock_transport(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={
                "action": "set_state",
                "power": True,
                "mode": "cool",
                "temperature_c": 24,
                "fan": "high",
            },
        )
        transmissions = client.get("/api/v1/ir/transmissions")

    assert response.status_code == 200
    result = response.json()
    assert result["device"]["icon"] == "snowflake"
    assert result["resolved_command"]["command_id"] == "cool_24_high"
    assert result["resolved_command"]["frames_hex"] == [
        ["b2", "4d", "3f", "c0", "40", "bf"],
        ["b2", "4d", "3f", "c0", "40", "bf"],
    ]
    assert result["transmission"]["status"] == "mock_recorded"
    assert result["transmission"]["hardware_output"] is False
    assert len(transmissions.json()["items"]) == 1


def test_power_off_uses_explicit_captured_packet(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "set_state", "power": False},
        )

    assert response.status_code == 200
    command = response.json()["resolved_command"]
    assert command["command_id"] == "power_off"
    assert command["source_capture"] == "power-off-from-cool-17-high-01"
    assert response.json()["device"]["last_desired_state"] == {
        "power": False,
        "confirmation": "inferred_from_ir_command",
    }


def test_toggle_command_does_not_replace_last_desired_state(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        state_response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={
                "action": "set_state",
                "power": True,
                "mode": "cool",
                "temperature_c": 24,
                "fan": "high",
            },
        )
        toggle_response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "execute", "command_id": "swing_toggle"},
        )

    assert state_response.status_code == 200
    assert toggle_response.status_code == 200
    device = toggle_response.json()["device"]
    assert device["last_desired_state"]["temperature_c"] == 24
    assert device["last_command"]["command_id"] == "swing_toggle"
    assert device["last_command"]["kind"] == "toggle"


def test_unknown_profile_and_invalid_semantic_command_are_rejected(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        unknown = client.post(
            "/api/v1/devices",
            json={"name": "unknown", "room": "room", "profile_id": "tv/None/Unknown"},
        )
        device_id = register_air_conditioner(client)
        missing_fan = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={
                "action": "set_state",
                "power": True,
                "mode": "cool",
                "temperature_c": 24,
            },
        )

    assert unknown.status_code == 422
    assert missing_fan.status_code == 422
    assert "fan must be one of" in missing_fan.json()["detail"]


def test_device_registration_rejects_invalid_icon_name(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/devices",
            json={
                "name": "거실 에어컨",
                "room": "거실",
                "profile_id": PROFILE_ID,
                "icon": "<script>",
            },
        )

    assert response.status_code == 422


def test_unsupported_model_request_persists_required_and_optional_files(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/device-requests",
            data={
                "device_type": "air_conditioner",
                "brand": "Example Brand",
                "model": "AC-1000",
            },
            files={
                "product_photo": ("product.jpg", b"\xff\xd8\xffjpeg-data", "image/jpeg"),
                "remote_photo": (
                    "remote.png",
                    b"\x89PNG\r\n\x1a\npng-data",
                    "image/png",
                ),
                "manual": ("manual.pdf", b"%PDF-1.7 pdf-data", "application/pdf"),
            },
        )

    assert response.status_code == 201
    request = response.json()
    assert request["status"] == "analysis_pending"
    assert set(request["files"]) == {"product_photo", "remote_photo", "manual"}
    request_root = tmp_path / "device_requests"
    for relative_path in request["files"].values():
        assert (request_root / relative_path).is_file()
    metadata = list(request_root.glob("air_conditioner/Example_Brand/AC-1000/requests/*.json"))
    assert len(metadata) == 1


def test_model_request_rejects_non_image_product_file(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/device-requests",
            data={"device_type": "air_conditioner", "brand": "Brand", "model": "Model"},
            files={"product_photo": ("notes.txt", b"not-an-image", "text/plain")},
        )

    assert response.status_code == 422
    assert "product_photo must use one of" in response.json()["detail"]
