import json
from pathlib import Path
from threading import Timer
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.service import DeviceService
from app.devices.store import RegisteredDeviceStore
from app.devices.transport import MockIrTransport
from app.integrations.mqtt import (
    H2_RESULT_TIMEOUT_SECONDS,
    DisabledSensorBridge,
    PahoSensorBridge,
    ZigbeeGatewayRequestError,
    ZigbeeGatewayUnavailableError,
    h2_request_from_command,
)
from app.ir.mock import MockReceiver
from app.main import create_app
from app.sensors.service import SensorService
from app.sensors.store import SensorStore
from app.settings import Settings
from tests.test_mqtt_bridge import FakeMqttClient

PROFILE_ID = "air_conditioner/Carrier/CS-A061GS"
PROFILE_ROOT = Path(__file__).parents[1] / "device_profiles"
H2_NAME = "h2_ir_01"


class FakeH2Bridge(DisabledSensorBridge):
    def __init__(self) -> None:
        self.sends = 0
        self.commands: list[dict[str, object]] = []
        self.timeouts: list[float] = []

    def devices(self) -> list[dict[str, object]]:
        return [{
            "friendly_name": H2_NAME,
            "model": "AIRCON_H2_IR_01",
            "supported": True,
            "interview_state": "SUCCESSFUL",
        }]

    def require_h2_device(self, friendly_name: str) -> dict[str, object]:
        if friendly_name != H2_NAME:
            raise ZigbeeGatewayUnavailableError("H2 is unavailable")
        return self.devices()[0]

    def send_h2_command(
        self, friendly_name: str, command: dict[str, object],
        timeout_seconds: float = H2_RESULT_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        self.require_h2_device(friendly_name)
        self.sends += 1
        self.commands.append(command)
        self.timeouts.append(timeout_seconds)
        return {
            "transport": "zigbee-h2-ir",
            "status": "sent",
            "request_id": 123,
            "hardware_output": True,
            "appliance_state_confirmed": False,
        }


def settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1", port=8001, log_level="INFO",
        data_dir=tmp_path, device_profiles_dir=PROFILE_ROOT,
    )


def test_existing_aircon_can_bind_h2_and_send_captured_commands(tmp_path: Path) -> None:
    bridge = FakeH2Bridge()
    app = create_app(settings(tmp_path), MockReceiver(), sensor_bridge=bridge)
    with TestClient(app) as client:
        created = client.post("/api/v1/devices", json={
            "name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID,
        })
        assert created.status_code == 201
        device_id = created.json()["id"]
        bound = client.put(f"/api/v1/devices/{device_id}/zigbee-h2", json={
            "friendly_name": H2_NAME,
        })
        assert bound.status_code == 200
        assert bound.json()["zigbee_binding"]["type"] == "h2_ir"

        cool = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": 24, "fan": "high",
        })
        assert cool.status_code == 200
        assert h2_request_from_command(bridge.commands[-1]) == {
            "command": "COOL_STATE", "temperature_c": 24, "fan": "high",
        }

        dry = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "dry",
        })
        assert dry.status_code == 200
        assert h2_request_from_command(bridge.commands[-1]) == {"command": "MODE_DRY"}

        swing = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "execute", "command_id": "swing_toggle",
        })
        assert swing.status_code == 200
        assert h2_request_from_command(bridge.commands[-1]) == {"command": "SWING_TOGGLE"}

        off = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": False,
        })
        assert off.status_code == 200
        assert bridge.sends == 4
        assert off.json()["transmission"]["transport"] == "zigbee-h2-ir"
        assert off.json()["transmission"]["appliance_state_confirmed"] is False
        assert off.json()["device"]["last_desired_state"]["power"] is False

        unbound = client.delete(f"/api/v1/devices/{device_id}/zigbee-h2")
        assert unbound.status_code == 200
        assert "zigbee_binding" not in unbound.json()
        assert bridge.sends == 4


def test_register_h2_is_atomic_and_rejects_duplicate_binding(tmp_path: Path) -> None:
    bridge = FakeH2Bridge()
    app = create_app(settings(tmp_path), MockReceiver(), sensor_bridge=bridge)
    payload = {
        "name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID,
        "zigbee_friendly_name": H2_NAME,
    }
    with TestClient(app) as client:
        invalid = client.post("/api/v1/devices", json={
            **payload, "zigbee_friendly_name": "unknown_h2",
        })
        assert invalid.status_code == 503
        assert client.get("/api/v1/devices").json()["items"] == []

        created = client.post("/api/v1/devices", json=payload)
        assert created.status_code == 201
        assert created.json()["zigbee_binding"]["friendly_name"] == H2_NAME

        duplicate = client.post("/api/v1/devices", json={**payload, "name": "다른 에어컨"})
        assert duplicate.status_code == 422
        assert len(client.get("/api/v1/devices").json()["items"]) == 1


def test_paho_h2_reply_matches_request_and_publishes_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_client = FakeMqttClient()
    monkeypatch.setattr("app.integrations.mqtt.mqtt.Client", lambda *_a, **_kw: fake_client)
    bridge = PahoSensorBridge(
        Settings(host="127.0.0.1", port=8001, log_level="INFO",
                 data_dir=tmp_path, mqtt_enabled=True),
        SensorService(store=SensorStore(tmp_path)),
    )
    bridge.start()
    assert fake_client.on_connect is not None
    fake_client.on_connect(fake_client, None, None, 0, None)
    assert fake_client.on_message is not None
    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic="zigbee2mqtt/bridge/devices",
        payload=json.dumps([{
            "type": "EndDevice", "friendly_name": H2_NAME,
            "supported": True, "interview_state": "SUCCESSFUL",
            "definition": {"model": "AIRCON_H2_IR_01"},
        }]).encode(),
    ))

    def publish_h2(topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
        assert qos == 0 and retain is False
        request = json.loads(payload)["ir_request"]
        fake_client.published.append((topic, request))
        for request_id, status in (
            (request["request_id"] + 1, "sent"),
            (request["request_id"], "accepted"),
            (request["request_id"], "sent"),
        ):
            fake_client.on_message(fake_client, None, SimpleNamespace(
                topic=f"zigbee2mqtt/{H2_NAME}",
                payload=json.dumps({"ir_result": {
                    "command": "POWER_OFF", "request_id": request_id, "status": status,
                }}).encode(),
            ))
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    fake_client.publish = publish_h2
    result = bridge.send_h2_command(H2_NAME, {"command_id": "power_off"})
    assert result["status"] == "sent"
    assert result["request_id"] == fake_client.published[0][1]["request_id"]
    assert len(fake_client.published) == 1
    assert fake_client.published[0][0] == f"zigbee2mqtt/{H2_NAME}/set"
    bridge.stop()


class FailingFollowUpH2Bridge(FakeH2Bridge):
    def send_h2_command(
        self, friendly_name: str, command: dict[str, object],
        timeout_seconds: float = H2_RESULT_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        if str(command["command_id"]).startswith("cool_") and self.commands and (
            self.commands[-1]["command_id"] == "economy"
        ):
            self.commands.append(command)
            raise ZigbeeGatewayRequestError("H2 IR result: failed")
        return super().send_h2_command(friendly_name, command, timeout_seconds)


class SlowH2Bridge(FakeH2Bridge):
    """Each H2 step takes `step_seconds` on a fake monotonic clock."""

    def __init__(self, step_seconds: float, follow_up_times_out: bool = False) -> None:
        super().__init__()
        self.now = 1000.0
        self.step_seconds = step_seconds
        self.follow_up_times_out = follow_up_times_out

    def send_h2_command(
        self, friendly_name: str, command: dict[str, object],
        timeout_seconds: float = H2_RESULT_TIMEOUT_SECONDS,
    ) -> dict[str, object]:
        result = super().send_h2_command(friendly_name, command, timeout_seconds)
        self.now += min(self.step_seconds, timeout_seconds)
        if self.follow_up_times_out and command["command_id"] != "economy":
            raise ZigbeeGatewayRequestError(
                "H2 result timed out; IR may have been sent. Check the appliance before retrying"
            )
        return result


@pytest.mark.parametrize(("step_seconds", "follow_up_timeout"), [(12.5, 5.5), (17.8, 1.0)])
def test_h2_economy_steps_share_one_result_budget(
    tmp_path: Path, step_seconds: float, follow_up_timeout: float
) -> None:
    bridge = SlowH2Bridge(step_seconds)
    catalog = DeviceProfileCatalog(PROFILE_ROOT)
    store = RegisteredDeviceStore(tmp_path)
    service = DeviceService(
        catalog=catalog, store=store, resolver=DeviceCommandResolver(catalog),
        transport=MockIrTransport(), zigbee_bridge=bridge, monotonic=lambda: bridge.now,
    )
    device = service.register(
        name="test", room="test", profile_id=PROFILE_ID, zigbee_friendly_name=H2_NAME,
    )
    service.execute(device["id"], {
        "action": "set_state", "power": True, "mode": "cool", "temperature_c": 26, "fan": "low",
    })
    bridge.timeouts.clear()

    service.execute(device["id"], {"action": "execute", "command_id": "economy"})
    # The central agent's 20 s local timeout assumes one 18 s H2 wait per command.
    assert bridge.timeouts == [H2_RESULT_TIMEOUT_SECONDS, follow_up_timeout]


def test_h2_economy_follow_up_timeout_records_nothing(tmp_path: Path) -> None:
    bridge = SlowH2Bridge(10.0)
    catalog = DeviceProfileCatalog(PROFILE_ROOT)
    store = RegisteredDeviceStore(tmp_path)
    service = DeviceService(
        catalog=catalog, store=store, resolver=DeviceCommandResolver(catalog),
        transport=MockIrTransport(), zigbee_bridge=bridge, monotonic=lambda: bridge.now,
    )
    device = service.register(
        name="test", room="test", profile_id=PROFILE_ID, zigbee_friendly_name=H2_NAME,
    )
    service.execute(device["id"], {
        "action": "set_state", "power": True, "mode": "cool", "temperature_c": 26, "fan": "low",
    })
    bridge.follow_up_times_out = True
    bridge.timeouts.clear()
    started = bridge.now

    with pytest.raises(ZigbeeGatewayRequestError, match="restoring the cooling state failed: H2"):
        service.execute(device["id"], {"action": "execute", "command_id": "economy"})
    assert bridge.timeouts == [H2_RESULT_TIMEOUT_SECONDS, 8.0]
    assert bridge.now - started == H2_RESULT_TIMEOUT_SECONDS
    stored = store.get(device["id"])
    assert stored["last_command"]["command_id"] == "cool_26_low"
    assert stored["last_desired_state"]["fan"] == "low"


def test_h2_economy_sends_eco_then_current_cool_state(tmp_path: Path) -> None:
    bridge = FakeH2Bridge()
    app = create_app(settings(tmp_path), MockReceiver(), sensor_bridge=bridge)
    with TestClient(app) as client:
        device_id = client.post("/api/v1/devices", json={
            "name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID,
            "zigbee_friendly_name": H2_NAME,
        }).json()["id"]
        client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": 26, "fan": "low",
        })
        economy = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "execute", "command_id": "economy",
        })

    assert economy.status_code == 200
    assert [h2_request_from_command(command) for command in bridge.commands[-2:]] == [
        {"command": "ECONOMY"},
        {"command": "COOL_STATE", "temperature_c": 26, "fan": "auto"},
    ]
    assert economy.json()["transmission"]["follow_up"]["status"] == "sent"
    state = economy.json()["device"]["last_desired_state"]
    assert (state["power"], state["mode"], state["temperature_c"], state["fan"]) == (
        True, "cool", 26, "auto",
    )


def test_h2_economy_follow_up_failure_is_reported_and_keeps_state(tmp_path: Path) -> None:
    bridge = FailingFollowUpH2Bridge()
    app = create_app(settings(tmp_path), MockReceiver(), sensor_bridge=bridge)
    with TestClient(app) as client:
        device_id = client.post("/api/v1/devices", json={
            "name": "거실 에어컨", "room": "거실", "profile_id": PROFILE_ID,
            "zigbee_friendly_name": H2_NAME,
        }).json()["id"]
        client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "set_state", "power": True, "mode": "cool",
            "temperature_c": 26, "fan": "low",
        })
        economy = client.post(f"/api/v1/devices/{device_id}/commands", json={
            "action": "execute", "command_id": "economy",
        })
        device = client.get("/api/v1/devices").json()["items"][0]

    assert economy.status_code == 502
    assert "restoring the cooling state failed" in economy.json()["detail"]
    assert [command["command_id"] for command in bridge.commands] == [
        "cool_26_low", "economy", "cool_26_auto",
    ]
    assert device["last_desired_state"]["fan"] == "low"
    assert device["last_command"]["command_id"] == "cool_26_low"


def make_paho_h2_bridge(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[PahoSensorBridge, FakeMqttClient]:
    fake_client = FakeMqttClient()
    monkeypatch.setattr("app.integrations.mqtt.mqtt.Client", lambda *_a, **_kw: fake_client)
    bridge = PahoSensorBridge(
        Settings(host="127.0.0.1", port=8001, log_level="INFO",
                 data_dir=tmp_path, mqtt_enabled=True),
        SensorService(store=SensorStore(tmp_path)),
    )
    bridge.start()
    assert fake_client.on_connect is not None and fake_client.on_message is not None
    fake_client.on_connect(fake_client, None, None, 0, None)
    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic="zigbee2mqtt/bridge/devices",
        payload=json.dumps([{
            "type": "EndDevice", "friendly_name": H2_NAME,
            "supported": True, "interview_state": "SUCCESSFUL",
            "definition": {"model": "AIRCON_H2_IR_01"},
        }]).encode(),
    ))
    return bridge, fake_client


def h2_result(fake_client: FakeMqttClient, request_id: int, status: str) -> None:
    assert fake_client.on_message is not None
    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic=f"zigbee2mqtt/{H2_NAME}",
        payload=json.dumps({"ir_result": {
            "command": "POWER_OFF", "request_id": request_id, "status": status,
        }}).encode(),
    ))


@pytest.mark.parametrize("delayed_sent", [True, False])
def test_paho_h2_duplicate_is_not_a_final_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, delayed_sent: bool
) -> None:
    bridge, fake_client = make_paho_h2_bridge(monkeypatch, tmp_path)

    def publish_h2(topic: str, payload: str, *, qos: int, retain: bool) -> SimpleNamespace:
        request_id = json.loads(payload)["ir_request"]["request_id"]
        fake_client.published.append((topic, {"request_id": request_id}))
        h2_result(fake_client, request_id, "accepted")
        if delayed_sent:
            # A retried copy reports duplicate while the original is still queued.
            h2_result(fake_client, request_id, "duplicate")
            Timer(0.2, h2_result, (fake_client, request_id, "sent")).start()
        else:
            # A late duplicate must not overwrite the first terminal result.
            h2_result(fake_client, request_id, "sent")
            h2_result(fake_client, request_id, "duplicate")
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    fake_client.publish = publish_h2
    result = bridge.send_h2_command(H2_NAME, {"command_id": "power_off"})
    assert result["status"] == "sent"
    assert len(fake_client.published) == 1
    bridge.stop()
