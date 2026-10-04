import json
from pathlib import Path
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest
from fastapi.testclient import TestClient

from app.integrations.mqtt import (
    DisabledSensorBridge,
    PahoSensorBridge,
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
        self, friendly_name: str, command: dict[str, object]
    ) -> dict[str, object]:
        self.require_h2_device(friendly_name)
        self.sends += 1
        self.commands.append(command)
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
