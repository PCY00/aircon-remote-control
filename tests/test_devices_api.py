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


def test_cool_state_uses_coolix_temperature_codes() -> None:
    from app.devices.catalog import DeviceProfileCatalog
    from app.devices.commands import DeviceCommandResolver

    resolver = DeviceCommandResolver(DeviceProfileCatalog(PROFILE_ROOT))

    def frame(temperature: int, fan: str = "auto") -> list[str]:
        command = resolver.resolve(PROFILE_ID, {
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": temperature, "fan": fan,
        })
        assert command["frames_hex"][0] == command["frames_hex"][1]
        return command["frames_hex"][0]

    # Plain Gray code gave f0 0f (27 C) and the fan-only code e0 1f (28 C).
    assert frame(27) == ["b2", "4d", "bf", "40", "90", "6f"]
    assert frame(28) == ["b2", "4d", "bf", "40", "80", "7f"]
    # Measured captures still match.
    assert [frame(temperature)[4] for temperature in (17, 18, 19, 20)] == ["00", "10", "30", "20"]
    for temperature in range(17, 31):
        for fan in ("auto", "low", "medium", "high"):
            assert int(frame(temperature, fan)[4], 16) >> 4 != 0xE


def test_economy_rebuilds_current_cool_state_and_records_it(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": 26, "fan": "low",
        })
        response = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "execute", "command_id": "economy"},
        )

    assert response.status_code == 200
    result = response.json()
    # Eco frame, then the current 26 C setpoint with fan auto (not the captured 17 C).
    assert result["resolved_command"]["frames_hex"] == [
        ["b2", "4d", "e0", "1f", "03", "fc"],
        ["b2", "4d", "bf", "40", "d0", "2f"],
        ["b2", "4d", "bf", "40", "d0", "2f"],
    ]
    assert result["device"]["last_desired_state"] == {
        "power": True, "mode": "cool", "temperature_c": 26, "fan": "auto",
        "confirmation": "inferred_from_ir_command",
    }
    assert result["device"]["last_command"]["command_id"] == "economy"


def test_economy_is_rejected_unless_cooling(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        economy = {"action": "execute", "command_id": "economy"}
        unknown_state = client.post(f"/api/v1/devices/{device_id}/commands", json=economy)
        client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "set_state", "power": False},
        )
        powered_off = client.post(f"/api/v1/devices/{device_id}/commands", json=economy)
        client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={"action": "set_state", "power": True, "mode": "dry"},
        )
        drying = client.post(f"/api/v1/devices/{device_id}/commands", json=economy)
        transmissions = client.get("/api/v1/ir/transmissions").json()["items"]
        device = client.get("/api/v1/devices").json()["items"][0]

    for response in (unknown_state, powered_off, drying):
        assert response.status_code == 422
        assert response.json()["detail"] == "economy requires the air conditioner to be cooling"
    assert [item["command"]["command_id"] for item in transmissions] == ["power_off", "mode_dry"]
    assert device["last_desired_state"]["mode"] == "dry"


def test_register_rejects_blank_name_or_room_and_strips_padding(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        blank_name = client.post("/api/v1/devices", json={
            "name": "   ", "room": "거실", "profile_id": PROFILE_ID,
        })
        blank_room = client.post("/api/v1/devices", json={
            "name": "거실 에어컨", "room": "  ", "profile_id": PROFILE_ID,
        })
        padded = client.post("/api/v1/devices", json={
            "name": "  거실 에어컨 ", "room": " 거실 ", "profile_id": PROFILE_ID,
        })

    assert blank_name.status_code == 422
    assert blank_room.status_code == 422
    assert padded.status_code == 201
    assert (padded.json()["name"], padded.json()["room"]) == ("거실 에어컨", "거실")


def test_model_request_accepts_empty_optional_file_parts(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    boundary = "----aircon-test-boundary"

    def part(name: str, value: bytes, filename: str | None = None) -> bytes:
        disposition = f'form-data; name="{name}"'
        headers = f"Content-Disposition: {disposition}"
        if filename is not None:
            headers += f'; filename="{filename}"\r\nContent-Type: application/octet-stream'
        return f"--{boundary}\r\n{headers}\r\n\r\n".encode() + value + b"\r\n"

    # What a browser sends for FormData(form) with the two optional inputs left empty.
    body = b"".join((
        part("device_type", b"air_conditioner"),
        part("brand", b"Brand"),
        part("model", b"Model"),
        part("product_photo", b"\xff\xd8\xffjpeg-data", "p.jpg"),
        part("remote_photo", b"", ""),
        part("manual", b"", ""),
    )) + f"--{boundary}--\r\n".encode()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/device-requests",
            content=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    assert response.status_code == 201
    assert set(response.json()["files"]) == {"product_photo"}
