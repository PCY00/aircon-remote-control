import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.ir.mock import MockReceiver
from app.main import create_app
from app.settings import Settings

PROFILE_ROOT = Path(__file__).parents[1] / "device_profiles"


def make_settings(data_dir: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8001,
        log_level="INFO",
        data_dir=data_dir,
        device_profiles_dir=PROFILE_ROOT,
        mqtt_enabled=False,
    )


def test_sensor_api_exposes_state_event_history_and_bridge_status(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    service = app.state.sensor_service
    service.ingest_mqtt("zigbee2mqtt/sensor_door_01", b'{"contact":true,"battery":100}')
    service.ingest_mqtt("zigbee2mqtt/sensor_door_01", b'{"contact":false}')
    service.ingest_mqtt(
        "zigbee2mqtt/sensor_temperature_01",
        json.dumps({"temperature": 25.5, "humidity": 40.0}).encode(),
    )

    with TestClient(app) as client:
        status = client.get("/api/v1/sensors/status")
        sensors = client.get("/api/v1/sensors")
        door = client.get("/api/v1/sensors/sensor_door_01")
        events = client.get("/api/v1/sensors/sensor_door_01/events?limit=10")

    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["stored_sensor_count"] == 2
    assert [item["device_id"] for item in sensors.json()["items"]] == [
        "sensor_door_01",
        "sensor_temperature_01",
    ]
    assert door.json()["state"]["door_state"] == "open"
    assert events.json()["items"][0]["state"] == "open"


def test_unknown_sensor_and_invalid_event_limit_are_rejected(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        missing = client.get("/api/v1/sensors/missing")
        missing_events = client.get("/api/v1/sensors/missing/events")
        invalid_limit = client.get("/api/v1/sensors/missing/events?limit=201")

    assert missing.status_code == 404
    assert missing_events.status_code == 404
    assert invalid_limit.status_code == 422


def test_sensor_metadata_is_shared_from_sqlite_and_survives_app_restart(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    app.state.sensor_service.ingest_mqtt(
        "zigbee2mqtt/sensor_door_01",
        b'{"contact":true}',
    )

    with TestClient(app) as client:
        updated = client.patch(
            "/api/v1/sensors/sensor_door_01/metadata",
            json={
                "display_name": "현관문",
                "room": "현관",
                "icon": "door-open",
            },
        )

    assert updated.status_code == 200
    assert updated.json()["metadata"]["display_name"] == "현관문"
    assert updated.json()["metadata"]["customized"] is True

    restored = create_app(make_settings(tmp_path), MockReceiver())
    with TestClient(restored) as client:
        sensor = client.get("/api/v1/sensors/sensor_door_01")

    assert sensor.json()["metadata"]["room"] == "현관"


def test_sensor_metadata_rejects_unknown_sensor_and_icon(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    app.state.sensor_service.ingest_mqtt(
        "zigbee2mqtt/sensor_door_01",
        b'{"contact":true}',
    )

    with TestClient(app) as client:
        missing = client.patch(
            "/api/v1/sensors/missing/metadata",
            json={"display_name": "센서", "room": "거실", "icon": "activity"},
        )
        invalid_icon = client.patch(
            "/api/v1/sensors/sensor_door_01/metadata",
            json={"display_name": "센서", "room": "거실", "icon": "skull"},
        )

    assert missing.status_code == 404
    assert invalid_icon.status_code == 422


class LifecycleBridge:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def status(self) -> dict[str, object]:
        return {"enabled": True, "running": self.started and not self.stopped}

    def join_status(self) -> dict[str, object]:
        return {"supported": True, "permit_join": False}

    def set_permit_join(self, duration_seconds: int) -> dict[str, object]:
        return {"supported": True, "permit_join": duration_seconds > 0}

    def devices(self) -> list[dict[str, object]]:
        return [{"friendly_name": "sensor_door_01", "supported": True}]


def test_sensor_bridge_follows_fastapi_lifecycle(tmp_path: Path) -> None:
    bridge = LifecycleBridge()
    app = create_app(make_settings(tmp_path), MockReceiver(), sensor_bridge=bridge)

    assert bridge.started is False
    with TestClient(app):
        assert bridge.started is True
        assert bridge.stopped is False
    assert bridge.stopped is True


def test_zigbee_join_api_is_bounded_and_uses_bridge(tmp_path: Path) -> None:
    bridge = LifecycleBridge()
    app = create_app(
        make_settings(tmp_path),
        MockReceiver(),
        sensor_bridge=bridge,
    )

    with TestClient(app) as client:
        opened = client.post("/api/v1/zigbee/join", json={"duration_seconds": 60})
        devices = client.get("/api/v1/zigbee/devices")
        closed = client.delete("/api/v1/zigbee/join")
        too_long = client.post("/api/v1/zigbee/join", json={"duration_seconds": 121})

    assert opened.json()["permit_join"] is True
    assert devices.json()["items"][0]["friendly_name"] == "sensor_door_01"
    assert closed.json()["permit_join"] is False
    assert too_long.status_code == 422
