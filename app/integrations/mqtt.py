"""Paho MQTT adapter for Zigbee2MQTT sensor reports."""

from __future__ import annotations

import json
import logging
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Protocol

import paho.mqtt.client as mqtt

from app.sensors.service import (
    InvalidSensorMessageError,
    SensorService,
    UnsupportedSensorMessageError,
)
from app.settings import Settings

LOGGER = logging.getLogger(__name__)
MAX_PERMIT_JOIN_SECONDS = 120


class ZigbeeGatewayUnavailableError(RuntimeError):
    """Raised when a bridge command cannot reach Zigbee2MQTT."""


class ZigbeeGatewayRequestError(RuntimeError):
    """Raised when Zigbee2MQTT rejects or does not answer a command."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SensorBridge(Protocol):
    """Lifecycle and status boundary used by FastAPI."""

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def status(self) -> dict[str, object]: ...

    def join_status(self) -> dict[str, object]: ...

    def set_permit_join(self, duration_seconds: int) -> dict[str, object]: ...

    def devices(self) -> list[dict[str, object]]: ...


class DisabledSensorBridge:
    """No-op bridge for local development and tests."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def status(self) -> dict[str, object]:
        return {
            "enabled": False,
            "running": False,
            "connected": False,
            "last_connected_at": None,
            "last_disconnected_at": None,
            "last_message_at": None,
            "last_error": None,
        }

    def join_status(self) -> dict[str, object]:
        return {
            "supported": False,
            "permit_join": False,
            "permit_join_end": None,
            "remaining_seconds": 0,
            "max_duration_seconds": MAX_PERMIT_JOIN_SECONDS,
        }

    def set_permit_join(self, duration_seconds: int) -> dict[str, object]:
        del duration_seconds
        raise ZigbeeGatewayUnavailableError("Zigbee MQTT bridge is disabled")

    def devices(self) -> list[dict[str, object]]:
        return []


class PahoSensorBridge:
    """Run the Paho network loop in a background thread and normalize messages."""

    def __init__(self, settings: Settings, service: SensorService) -> None:
        self._settings = settings
        self._service = service
        self._lock = Lock()
        self._running = False
        self._connected = False
        self._last_connected_at: str | None = None
        self._last_disconnected_at: str | None = None
        self._last_message_at: str | None = None
        self._last_error: str | None = None
        self._bridge_info: dict[str, object] = {}
        self._devices: list[dict[str, object]] = []
        self._pending_requests: dict[str, dict[str, object]] = {}
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.mqtt_client_id,
            protocol=mqtt.MQTTv311,
        )
        if settings.mqtt_username:
            self._client.username_pw_set(
                settings.mqtt_username,
                settings.mqtt_password,
            )
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.enable_logger(LOGGER)
        self._client.on_connect = self._on_connect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._last_error = None
        try:
            self._client.connect_async(
                self._settings.mqtt_host,
                self._settings.mqtt_port,
                self._settings.mqtt_keepalive_seconds,
            )
            result = self._client.loop_start()
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT network loop failed to start: {result}")
        except Exception as exc:
            with self._lock:
                self._running = False
                self._last_error = str(exc)
            raise

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
        self._client.disconnect()
        self._client.loop_stop()
        with self._lock:
            self._connected = False
            for pending in self._pending_requests.values():
                pending["response"] = {
                    "status": "error",
                    "error": "MQTT bridge stopped",
                }
                event = pending["event"]
                if isinstance(event, Event):
                    event.set()

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "enabled": True,
                "running": self._running,
                "connected": self._connected,
                "last_connected_at": self._last_connected_at,
                "last_disconnected_at": self._last_disconnected_at,
                "last_message_at": self._last_message_at,
                "last_error": self._last_error,
            }

    def join_status(self) -> dict[str, object]:
        with self._lock:
            enabled = bool(self._bridge_info.get("permit_join", False))
            raw_end = self._bridge_info.get("permit_join_end")
        end = int(raw_end) if isinstance(raw_end, int | float) else None
        now = int(time.time())
        if end is not None and end <= now:
            enabled = False
            end = None
        return {
            "supported": True,
            "permit_join": enabled,
            "permit_join_end": end,
            "remaining_seconds": max(0, end - now) if enabled and end is not None else 0,
            "max_duration_seconds": MAX_PERMIT_JOIN_SECONDS,
        }

    def set_permit_join(self, duration_seconds: int) -> dict[str, object]:
        if not 0 <= duration_seconds <= MAX_PERMIT_JOIN_SECONDS:
            raise ValueError(
                f"permit join duration must be between 0 and {MAX_PERMIT_JOIN_SECONDS} seconds"
            )
        with self._lock:
            if not self._running or not self._connected:
                raise ZigbeeGatewayUnavailableError("Zigbee2MQTT is not connected")
            transaction = uuid.uuid4().hex
            event = Event()
            self._pending_requests[transaction] = {"event": event, "response": None}

        payload = json.dumps(
            {"time": duration_seconds, "transaction": transaction},
            separators=(",", ":"),
        )
        result = self._client.publish(
            f"{self._service.base_topic}/bridge/request/permit_join",
            payload,
            qos=0,
            retain=False,
        )
        if getattr(result, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
            with self._lock:
                self._pending_requests.pop(transaction, None)
            raise ZigbeeGatewayRequestError("failed to publish permit_join request")

        if not event.wait(timeout=8):
            with self._lock:
                self._pending_requests.pop(transaction, None)
                self._last_error = "permit_join response timed out"
            raise ZigbeeGatewayRequestError("Zigbee2MQTT permit_join response timed out")

        with self._lock:
            pending = self._pending_requests.pop(transaction, None)
            response = pending.get("response") if pending is not None else None
        if not isinstance(response, dict):
            raise ZigbeeGatewayRequestError("invalid Zigbee2MQTT permit_join response")
        if response.get("status") != "ok":
            error = response.get("error")
            raise ZigbeeGatewayRequestError(
                str(error)
                if isinstance(error, str) and error
                else "Zigbee2MQTT rejected permit_join"
            )

        with self._lock:
            self._bridge_info["permit_join"] = duration_seconds > 0
            self._bridge_info["permit_join_end"] = (
                int(time.time()) + duration_seconds if duration_seconds > 0 else None
            )
            self._last_error = None
        return self.join_status()

    def devices(self) -> list[dict[str, object]]:
        with self._lock:
            return deepcopy(self._devices)

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            with self._lock:
                self._connected = False
                self._last_error = f"MQTT connection refused: {reason_code}"
            return
        for topic in (
            f"{self._service.base_topic}/+",
            f"{self._service.base_topic}/bridge/info",
            f"{self._service.base_topic}/bridge/devices",
            f"{self._service.base_topic}/bridge/response/permit_join",
        ):
            client.subscribe(topic, qos=0)
        with self._lock:
            self._connected = True
            self._last_connected_at = _now()
            self._last_error = None

    def _on_connect_fail(self, _client: mqtt.Client, _userdata: object) -> None:
        with self._lock:
            self._connected = False
            self._last_error = "MQTT connection attempt failed"

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        with self._lock:
            self._connected = False
            self._last_disconnected_at = _now()
            if self._running and reason_code != 0:
                self._last_error = f"MQTT disconnected: {reason_code}"

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        payload_bytes = bytes(message.payload)
        if message.topic == f"{self._service.base_topic}/bridge/info":
            self._handle_bridge_info(payload_bytes)
            return
        if message.topic == f"{self._service.base_topic}/bridge/devices":
            self._handle_bridge_devices(payload_bytes)
            return
        if message.topic == f"{self._service.base_topic}/bridge/response/permit_join":
            self._handle_permit_join_response(payload_bytes)
            return
        try:
            self._service.ingest_mqtt(message.topic, payload_bytes)
        except (InvalidSensorMessageError, UnsupportedSensorMessageError) as exc:
            LOGGER.debug("Ignored MQTT message on %s: %s", message.topic, exc)
            return
        except Exception:
            LOGGER.exception("Failed to persist MQTT sensor message from %s", message.topic)
            with self._lock:
                self._last_error = "failed to persist a sensor message"
            return
        with self._lock:
            self._last_message_at = _now()
            self._last_error = None

    @staticmethod
    def _decode_json(payload: bytes) -> object:
        if len(payload) > 1024 * 1024:
            raise ValueError("Zigbee bridge payload exceeds the size limit")
        return json.loads(payload.decode("utf-8"))

    def _handle_bridge_info(self, payload: bytes) -> None:
        try:
            decoded = self._decode_json(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            LOGGER.warning("Ignored invalid Zigbee2MQTT bridge/info payload")
            return
        if not isinstance(decoded, dict):
            return
        raw_end = decoded.get("permit_join_end")
        with self._lock:
            self._bridge_info = {
                "permit_join": bool(decoded.get("permit_join", False)),
                "permit_join_end": (
                    int(raw_end) if isinstance(raw_end, int | float) else None
                ),
            }
            self._last_message_at = _now()

    def _handle_bridge_devices(self, payload: bytes) -> None:
        try:
            decoded = self._decode_json(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            LOGGER.warning("Ignored invalid Zigbee2MQTT bridge/devices payload")
            return
        if not isinstance(decoded, list):
            return
        devices: list[dict[str, object]] = []
        for raw_device in decoded:
            if not isinstance(raw_device, dict) or raw_device.get("type") == "Coordinator":
                continue
            friendly_name = raw_device.get("friendly_name")
            if not isinstance(friendly_name, str) or not friendly_name.strip():
                continue
            definition = raw_device.get("definition")
            definition = definition if isinstance(definition, dict) else {}
            devices.append(
                {
                    "friendly_name": friendly_name[:200],
                    "supported": bool(raw_device.get("supported", False)),
                    "interview_state": raw_device.get("interview_state"),
                    "interviewing": bool(raw_device.get("interviewing", False)),
                    "model_id": raw_device.get("model_id"),
                    "power_source": raw_device.get("power_source"),
                    "vendor": definition.get("vendor"),
                    "model": definition.get("model"),
                    "description": definition.get("description"),
                }
            )
        devices.sort(key=lambda item: str(item["friendly_name"]).casefold())
        with self._lock:
            self._devices = devices
            self._last_message_at = _now()

    def _handle_permit_join_response(self, payload: bytes) -> None:
        try:
            decoded = self._decode_json(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            LOGGER.warning("Ignored invalid Zigbee2MQTT permit_join response")
            return
        if not isinstance(decoded, dict):
            return
        transaction = decoded.get("transaction")
        if not isinstance(transaction, str):
            return
        with self._lock:
            pending = self._pending_requests.get(transaction)
            if pending is None:
                return
            pending["response"] = decoded
            event = pending["event"]
            if isinstance(event, Event):
                event.set()
            self._last_message_at = _now()
