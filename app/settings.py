"""Runtime settings loaded from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path


def _read_port() -> int:
    raw_value = os.getenv("AIRCON_PORT", "8001")
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_PORT must be an integer") from exc

    if not 1 <= port <= 65535:
        raise ValueError("AIRCON_PORT must be between 1 and 65535")
    return port


def _read_capture_timeout() -> float:
    raw_value = os.getenv("AIRCON_IR_CAPTURE_TIMEOUT", "90")
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_IR_CAPTURE_TIMEOUT must be a number") from exc

    if not 1 <= timeout <= 300:
        raise ValueError("AIRCON_IR_CAPTURE_TIMEOUT must be between 1 and 300 seconds")
    return timeout


def _read_send_timeout() -> float:
    raw_value = os.getenv("AIRCON_IR_SEND_TIMEOUT", "5")
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_IR_SEND_TIMEOUT must be a number") from exc

    if not 0.5 <= timeout <= 30:
        raise ValueError("AIRCON_IR_SEND_TIMEOUT must be between 0.5 and 30 seconds")
    return timeout


def _read_ir_transport() -> str:
    transport = os.getenv("AIRCON_IR_TRANSPORT", "mock").strip().lower()
    if transport not in {"mock", "ir-ctl"}:
        raise ValueError("AIRCON_IR_TRANSPORT must be mock or ir-ctl")
    return transport


def _read_max_upload_bytes() -> int:
    raw_value = os.getenv("AIRCON_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_MAX_UPLOAD_BYTES must be an integer") from exc

    if not 1024 <= value <= 50 * 1024 * 1024:
        raise ValueError("AIRCON_MAX_UPLOAD_BYTES must be between 1024 and 52428800")
    return value


def _read_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _read_mqtt_port() -> int:
    raw_value = os.getenv("AIRCON_MQTT_PORT", "1883")
    try:
        port = int(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_MQTT_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("AIRCON_MQTT_PORT must be between 1 and 65535")
    return port


def _read_mqtt_keepalive() -> int:
    raw_value = os.getenv("AIRCON_MQTT_KEEPALIVE_SECONDS", "60")
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError("AIRCON_MQTT_KEEPALIVE_SECONDS must be an integer") from exc
    if not 10 <= value <= 3600:
        raise ValueError("AIRCON_MQTT_KEEPALIVE_SECONDS must be between 10 and 3600")
    return value


def _read_mqtt_base_topic() -> str:
    value = os.getenv("AIRCON_MQTT_BASE_TOPIC", "zigbee2mqtt").strip().strip("/")
    if not value or "+" in value or "#" in value:
        raise ValueError("AIRCON_MQTT_BASE_TOPIC must be a non-wildcard MQTT topic")
    return value


@dataclass(frozen=True)
class Settings:
    """Application and IR receiver settings."""

    host: str
    port: int
    log_level: str
    data_dir: Path = Path("runtime")
    device_profiles_dir: Path = Path("device_profiles")
    ir_ctl_path: str = "ir-ctl"
    ir_receiver_device: Path = Path("/dev/lirc0")
    ir_capture_timeout_seconds: float = 90.0
    ir_transport: str = "mock"
    ir_transmitter_device: Path = Path("/dev/lirc0")
    ir_send_timeout_seconds: float = 5.0
    max_upload_bytes: int = 10 * 1024 * 1024
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_base_topic: str = "zigbee2mqtt"
    mqtt_client_id: str = "aircon-controller"
    mqtt_keepalive_seconds: int = 60


def load_settings() -> Settings:
    """Load application settings from the current process environment."""

    return Settings(
        host=os.getenv("AIRCON_HOST", "127.0.0.1"),
        port=_read_port(),
        log_level=os.getenv("AIRCON_LOG_LEVEL", "INFO").upper(),
        data_dir=Path(os.getenv("AIRCON_DATA_DIR", "runtime")),
        device_profiles_dir=Path(os.getenv("AIRCON_DEVICE_PROFILES_DIR", "device_profiles")),
        ir_ctl_path=os.getenv("AIRCON_IR_CTL_PATH", "ir-ctl"),
        ir_receiver_device=Path(os.getenv("AIRCON_IR_RECEIVER_DEVICE", "/dev/lirc0")),
        ir_capture_timeout_seconds=_read_capture_timeout(),
        ir_transport=_read_ir_transport(),
        ir_transmitter_device=Path(
            os.getenv("AIRCON_IR_TRANSMITTER_DEVICE", "/dev/lirc0")
        ),
        ir_send_timeout_seconds=_read_send_timeout(),
        max_upload_bytes=_read_max_upload_bytes(),
        mqtt_enabled=_read_bool("AIRCON_MQTT_ENABLED", False),
        mqtt_host=os.getenv("AIRCON_MQTT_HOST", "127.0.0.1").strip(),
        mqtt_port=_read_mqtt_port(),
        mqtt_username=os.getenv("AIRCON_MQTT_USERNAME") or None,
        mqtt_password=os.getenv("AIRCON_MQTT_PASSWORD") or None,
        mqtt_base_topic=_read_mqtt_base_topic(),
        mqtt_client_id=os.getenv("AIRCON_MQTT_CLIENT_ID", "aircon-controller").strip(),
        mqtt_keepalive_seconds=_read_mqtt_keepalive(),
    )
