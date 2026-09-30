from pathlib import Path

import pytest

from app.settings import load_settings


def test_mqtt_settings_are_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AIRCON_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AIRCON_MQTT_ENABLED", "yes")
    monkeypatch.setenv("AIRCON_MQTT_HOST", "mqtt.internal")
    monkeypatch.setenv("AIRCON_MQTT_PORT", "2883")
    monkeypatch.setenv("AIRCON_MQTT_USERNAME", "controller")
    monkeypatch.setenv("AIRCON_MQTT_PASSWORD", "test-only")
    monkeypatch.setenv("AIRCON_MQTT_BASE_TOPIC", "/zigbee2mqtt/")
    monkeypatch.setenv("AIRCON_MQTT_CLIENT_ID", "dashboard")
    monkeypatch.setenv("AIRCON_MQTT_KEEPALIVE_SECONDS", "90")

    settings = load_settings()

    assert settings.mqtt_enabled is True
    assert settings.mqtt_host == "mqtt.internal"
    assert settings.mqtt_port == 2883
    assert settings.mqtt_username == "controller"
    assert settings.mqtt_password == "test-only"
    assert settings.mqtt_base_topic == "zigbee2mqtt"
    assert settings.mqtt_client_id == "dashboard"
    assert settings.mqtt_keepalive_seconds == 90


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AIRCON_MQTT_ENABLED", "sometimes", "must be true or false"),
        ("AIRCON_MQTT_PORT", "70000", "between 1 and 65535"),
        ("AIRCON_MQTT_KEEPALIVE_SECONDS", "5", "between 10 and 3600"),
        ("AIRCON_MQTT_BASE_TOPIC", "zigbee/#", "non-wildcard MQTT topic"),
    ],
)
def test_invalid_mqtt_settings_fail_early(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    message: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=message):
        load_settings()
