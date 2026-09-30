"""Validate and normalize Zigbee2MQTT device reports."""

from __future__ import annotations

import json
import logging
import math
import re
from collections.abc import Callable
from datetime import UTC, datetime

from app.sensors.models import SensorUpdate
from app.sensors.store import SensorStore

LOGGER = logging.getLogger(__name__)

DEVICE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
RESERVED_DEVICE_IDS = {"bridge"}
ALLOWED_SENSOR_ICONS = {
    "activity",
    "door-open",
    "droplets",
    "radio-tower",
    "thermometer-sun",
}


class InvalidSensorMessageError(ValueError):
    """Raised when an MQTT message cannot safely become sensor state."""


class UnsupportedSensorMessageError(ValueError):
    """Raised when a valid JSON payload has no supported sensor fields."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _number(
    payload: dict[str, object],
    source: str,
    target: str,
    changes: dict[str, object],
    *,
    minimum: float,
    maximum: float,
) -> None:
    value = payload.get(source)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        return
    changes[target] = value


def _source_timestamp(payload: dict[str, object]) -> datetime | None:
    raw_value = payload.get("last_seen")
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    value = raw_value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


class SensorService:
    """Convert MQTT messages into a small stable sensor API."""

    def __init__(
        self,
        *,
        store: SensorStore,
        base_topic: str = "zigbee2mqtt",
        max_payload_bytes: int = 64 * 1024,
        clock: Callable[[], datetime] = _utc_now,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._store = store
        self.base_topic = base_topic.strip("/")
        self._max_payload_bytes = max_payload_bytes
        self._clock = clock
        self._listeners: list[Callable[[dict[str, object]], None]] = []
        if on_update is not None:
            self._listeners.append(on_update)

    def add_listener(self, listener: Callable[[dict[str, object]], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, sensor: dict[str, object]) -> None:
        for listener in tuple(self._listeners):
            try:
                listener(sensor)
            except Exception:
                LOGGER.exception("sensor update listener failed")

    def _device_id_from_topic(self, topic: str) -> str:
        prefix = f"{self.base_topic}/"
        if not topic.startswith(prefix):
            raise InvalidSensorMessageError("message is outside the configured base topic")
        device_id = topic[len(prefix) :]
        if (
            not DEVICE_ID_PATTERN.fullmatch(device_id)
            or device_id in RESERVED_DEVICE_IDS
        ):
            raise InvalidSensorMessageError("message does not target a sensor device")
        return device_id

    def ingest_mqtt(self, topic: str, payload_bytes: bytes) -> dict[str, object]:
        if len(payload_bytes) > self._max_payload_bytes:
            raise InvalidSensorMessageError("sensor payload exceeds the size limit")
        try:
            decoded = payload_bytes.decode("utf-8")
            payload = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidSensorMessageError("sensor payload must be a UTF-8 JSON object") from exc
        if not isinstance(payload, dict):
            raise InvalidSensorMessageError("sensor payload must be a JSON object")

        device_id = self._device_id_from_topic(topic)
        previous = self._store.get_optional(device_id)
        previous_kind = str(previous["kind"]) if previous is not None else None
        changes: dict[str, object] = {}

        contact = payload.get("contact")
        if isinstance(contact, bool):
            changes["contact"] = contact
            changes["door_state"] = "closed" if contact else "open"

        for source, target in (("tamper", "tamper"), ("battery_low", "battery_low")):
            value = payload.get(source)
            if isinstance(value, bool):
                changes[target] = value

        _number(
            payload,
            "temperature",
            "temperature_c",
            changes,
            minimum=-100,
            maximum=200,
        )
        _number(
            payload,
            "humidity",
            "humidity_percent",
            changes,
            minimum=0,
            maximum=100,
        )
        _number(
            payload,
            "battery",
            "battery_percent",
            changes,
            minimum=0,
            maximum=100,
        )
        _number(
            payload,
            "voltage",
            "voltage_mv",
            changes,
            minimum=0,
            maximum=100_000,
        )
        _number(
            payload,
            "linkquality",
            "linkquality",
            changes,
            minimum=0,
            maximum=1_000,
        )

        if isinstance(contact, bool):
            kind = "door_contact"
        elif "temperature_c" in changes or "humidity_percent" in changes:
            kind = "temperature_humidity"
        elif previous_kind is not None and changes:
            kind = previous_kind
        else:
            raise UnsupportedSensorMessageError("payload has no supported sensor fields")

        received_at = self._clock()
        if received_at.tzinfo is None:
            raise ValueError("sensor service clock must return a timezone-aware datetime")
        update = SensorUpdate(
            device_id=device_id,
            kind=kind,
            changes=changes,
            raw_payload=payload,
            received_at=received_at,
            source_timestamp=_source_timestamp(payload),
        )
        sensor = self._store.apply(update)
        self._notify(sensor)
        return sensor

    def list(self) -> list[dict[str, object]]:
        return self._store.list()

    def get(self, device_id: str) -> dict[str, object]:
        return self._store.get(device_id)

    def list_events(self, device_id: str, limit: int = 50) -> list[dict[str, object]]:
        return self._store.list_door_events(device_id, limit)

    def update_metadata(
        self,
        device_id: str,
        *,
        display_name: str,
        room: str,
        icon: str,
    ) -> dict[str, object]:
        """Persist one sensor's user-facing identity for every dashboard client."""

        normalized_name = display_name.strip()
        normalized_room = room.strip()
        if not normalized_name:
            raise ValueError("sensor display name must not be blank")
        if not normalized_room:
            raise ValueError("sensor room must not be blank")
        if icon not in ALLOWED_SENSOR_ICONS:
            raise ValueError("unsupported sensor icon")
        sensor = self._store.set_metadata(
            device_id,
            display_name=normalized_name,
            room=normalized_room,
            icon=icon,
            updated_at=self._clock(),
        )
        self._notify(sensor)
        return sensor
