import json
from pathlib import Path
from types import SimpleNamespace

import paho.mqtt.client as mqtt
import pytest

from app.integrations.mqtt import PahoSensorBridge
from app.sensors.service import SensorService
from app.sensors.store import SensorStore
from app.settings import Settings


class FakeMqttClient:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.on_connect = None
        self.on_connect_fail = None
        self.on_disconnect = None
        self.on_message = None
        self.username: str | None = None
        self.password: str | None = None
        self.connection: tuple[str, int, int] | None = None
        self.subscriptions: list[tuple[str, int]] = []
        self.published: list[tuple[str, dict[str, object]]] = []
        self.loop_started = False
        self.disconnected = False

    def username_pw_set(self, username: str, password: str | None) -> None:
        self.username = username
        self.password = password

    def reconnect_delay_set(self, *, min_delay: int, max_delay: int) -> None:
        assert (min_delay, max_delay) == (1, 30)

    def enable_logger(self, _logger: object) -> None:
        return None

    def connect_async(self, host: str, port: int, keepalive: int) -> None:
        self.connection = (host, port, keepalive)

    def loop_start(self) -> mqtt.MQTTErrorCode:
        self.loop_started = True
        return mqtt.MQTT_ERR_SUCCESS

    def subscribe(self, topic: str, qos: int) -> None:
        self.subscriptions.append((topic, qos))

    def publish(
        self,
        topic: str,
        payload: str,
        *,
        qos: int,
        retain: bool,
    ) -> SimpleNamespace:
        assert qos == 0
        assert retain is False
        decoded = json.loads(payload)
        self.published.append((topic, decoded))
        if topic.endswith("/bridge/request/permit_join"):
            assert self.on_message is not None
            self.on_message(
                self,
                None,
                SimpleNamespace(
                    topic="zigbee2mqtt/bridge/response/permit_join",
                    payload=json.dumps(
                        {
                            "data": {"time": decoded["time"]},
                            "status": "ok",
                            "transaction": decoded["transaction"],
                        }
                    ).encode(),
                ),
            )
        return SimpleNamespace(rc=mqtt.MQTT_ERR_SUCCESS)

    def disconnect(self) -> None:
        self.disconnected = True

    def loop_stop(self) -> None:
        self.loop_started = False


def test_paho_bridge_connects_subscribes_and_persists_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeMqttClient()
    monkeypatch.setattr(
        "app.integrations.mqtt.mqtt.Client",
        lambda *_args, **_kwargs: fake_client,
    )
    settings = Settings(
        host="127.0.0.1",
        port=8001,
        log_level="INFO",
        data_dir=tmp_path,
        mqtt_enabled=True,
        mqtt_host="mqtt.internal",
        mqtt_port=2883,
        mqtt_username="controller",
        mqtt_password="test-only",
        mqtt_keepalive_seconds=90,
    )
    service = SensorService(store=SensorStore(tmp_path))
    bridge = PahoSensorBridge(settings, service)

    bridge.start()
    assert fake_client.connection == ("mqtt.internal", 2883, 90)
    assert (fake_client.username, fake_client.password) == ("controller", "test-only")
    assert fake_client.on_connect is not None
    fake_client.on_connect(fake_client, None, None, 0, None)
    assert fake_client.subscriptions == [
        ("zigbee2mqtt/+", 0),
        ("zigbee2mqtt/bridge/info", 0),
        ("zigbee2mqtt/bridge/devices", 0),
        ("zigbee2mqtt/bridge/response/permit_join", 0),
    ]

    assert fake_client.on_message is not None
    fake_client.on_message(
        fake_client,
        None,
        SimpleNamespace(
            topic="zigbee2mqtt/sensor_door_01",
            payload=b'{"contact":false}',
        ),
    )

    assert service.get("sensor_door_01")["state"]["door_state"] == "open"
    assert bridge.status()["connected"] is True
    assert bridge.status()["last_message_at"] is not None

    bridge.stop()
    assert fake_client.disconnected is True
    assert bridge.status()["running"] is False


def test_paho_bridge_tracks_devices_and_opens_then_closes_joining(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeMqttClient()
    monkeypatch.setattr(
        "app.integrations.mqtt.mqtt.Client",
        lambda *_args, **_kwargs: fake_client,
    )
    settings = Settings(
        host="127.0.0.1",
        port=8001,
        log_level="INFO",
        data_dir=tmp_path,
        mqtt_enabled=True,
    )
    bridge = PahoSensorBridge(settings, SensorService(store=SensorStore(tmp_path)))
    bridge.start()
    assert fake_client.on_connect is not None
    fake_client.on_connect(fake_client, None, None, 0, None)

    assert fake_client.on_message is not None
    fake_client.on_message(
        fake_client,
        None,
        SimpleNamespace(
            topic="zigbee2mqtt/bridge/devices",
            payload=json.dumps(
                [
                    {"type": "Coordinator", "friendly_name": "Coordinator"},
                    {
                        "type": "EndDevice",
                        "friendly_name": "sensor_door_01",
                        "supported": True,
                        "interview_state": "SUCCESSFUL",
                        "model_id": "TS0203",
                        "power_source": "Battery",
                        "definition": {
                            "vendor": "Tuya",
                            "model": "TS0203",
                            "description": "Contact sensor",
                        },
                    },
                ]
            ).encode(),
        ),
    )

    assert bridge.devices() == [
        {
            "friendly_name": "sensor_door_01",
            "supported": True,
            "interview_state": "SUCCESSFUL",
            "interviewing": False,
            "model_id": "TS0203",
            "power_source": "Battery",
            "vendor": "Tuya",
            "model": "TS0203",
            "description": "Contact sensor",
        }
    ]
    opened = bridge.set_permit_join(60)
    assert opened["permit_join"] is True
    assert 1 <= opened["remaining_seconds"] <= 60

    closed = bridge.set_permit_join(0)
    assert closed["permit_join"] is False
    assert [item[1]["time"] for item in fake_client.published] == [60, 0]
