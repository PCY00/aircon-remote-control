import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.automations.service import AutomationService
from app.automations.store import AutomationStore
from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.service import DeviceService
from app.devices.store import RegisteredDeviceStore
from app.devices.transport import MockIrTransport
from app.events import EventHub
from app.integrations.mqtt import DisabledSensorBridge
from app.ir.mock import MockReceiver
from app.main import create_app
from app.sensors.service import SensorService
from app.sensors.store import SensorStore
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


def test_door_open_aircon_rule_records_one_warning_after_delay(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        powered = client.post(
            f"/api/v1/devices/{device_id}/commands",
            json={
                "action": "set_state",
                "power": True,
                "mode": "cool",
                "temperature_c": 24,
                "fan": "high",
            },
        )
        assert powered.status_code == 200
        app.state.sensor_service.ingest_mqtt(
            "zigbee2mqtt/sensor_door_01", b'{"contact":false}'
        )
        current = client.get("/api/v1/automations").json()["items"][0]
        started_at = datetime.fromisoformat(current["state"]["condition_started_at"])

        first = app.state.automation_service.evaluate(
            now=started_at + timedelta(seconds=301)
        )
        second = app.state.automation_service.evaluate(
            now=started_at + timedelta(seconds=302)
        )
        app.state.sensor_service.ingest_mqtt(
            "zigbee2mqtt/sensor_door_01", b'{"contact":true}'
        )
        resolved = client.get("/api/v1/automations").json()["items"][0]
        history = client.get("/api/v1/automations/events?limit=20")

    assert first["state"]["warning_active"] is True
    assert second["state"]["warning_active"] is True
    assert resolved["state"]["warning_active"] is False
    assert history.status_code == 200
    assert {item["event_type"] for item in history.json()["items"]} == {
        "warning_triggered",
        "warning_resolved",
    }


def test_rule_configuration_persists_and_validates_updates(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())

    with TestClient(app) as client:
        updated = client.patch(
            "/api/v1/automations/door-open-aircon-warning",
            json={"enabled": False, "delay_seconds": 600},
        )
        empty = client.patch(
            "/api/v1/automations/door-open-aircon-warning", json={}
        )
        missing = client.patch(
            "/api/v1/automations/missing", json={"enabled": True}
        )

    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["delay_seconds"] == 600
    assert empty.status_code == 422
    assert missing.status_code == 404

    restored = create_app(make_settings(tmp_path), MockReceiver())
    with TestClient(restored) as client:
        rule = client.get("/api/v1/automations").json()["items"][0]

    assert rule["enabled"] is False
    assert rule["delay_seconds"] == 600


def test_live_event_stream_is_published_in_openapi(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path), MockReceiver())
    assert "/api/v1/events" in app.openapi()["paths"]


class KnownSensorsBridge(DisabledSensorBridge):
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def devices(self) -> list[dict[str, object]]:
        return [{"friendly_name": name, "supported": True} for name in self.names]


def test_renamed_ghost_door_sensor_does_not_trigger_warning(tmp_path: Path) -> None:
    bridge = KnownSensorsBridge(["sensor_door_01"])
    app = create_app(make_settings(tmp_path), MockReceiver(), sensor_bridge=bridge)

    with TestClient(app) as client:
        device_id = register_air_conditioner(client)
        client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": 24, "fan": "high",
        })
        sensors = app.state.sensor_service
        # Paired in hand with the magnet apart, then renamed by rename_zigbee_devices.sh.
        sensors.ingest_mqtt("zigbee2mqtt/0x00124b0029a1b2c3", b'{"contact":false}')
        sensors.ingest_mqtt("zigbee2mqtt/sensor_door_01", b'{"contact":true}')
        known = client.get("/api/v1/automations").json()["items"][0]

        bridge.names = []  # bridge/devices not received yet: do not filter.
        unknown = client.get("/api/v1/automations").json()["items"][0]

    assert known["condition"]["open_doors"] == []
    assert known["condition"]["active"] is False
    assert [door["device_id"] for door in unknown["condition"]["open_doors"]] == [
        "0x00124b0029a1b2c3"
    ]


def test_automation_loop_survives_evaluate_error(tmp_path: Path) -> None:
    sensors = SensorService(store=SensorStore(tmp_path))
    catalog = DeviceProfileCatalog(PROFILE_ROOT)
    devices = DeviceService(
        catalog=catalog, store=RegisteredDeviceStore(tmp_path),
        resolver=DeviceCommandResolver(catalog), transport=MockIrTransport(),
    )
    service = AutomationService(
        store=AutomationStore(tmp_path), sensors=sensors, devices=devices,
        events=EventHub(), poll_seconds=0.01,
    )
    calls: list[int] = []
    original = service.evaluate

    def flaky_evaluate(**kwargs: object) -> dict[str, object]:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return original(**kwargs)

    service.evaluate = flaky_evaluate  # type: ignore[method-assign]

    async def run() -> None:
        service.start()
        for _ in range(200):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0.01)
        await service.stop()

    asyncio.run(run())
    assert len(calls) >= 3
