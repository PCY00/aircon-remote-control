"""Paho MQTT adapter for Zigbee2MQTT sensor reports."""

from __future__ import annotations

import json
import logging
import re
import secrets
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
H2_IR_MODEL = "AIRCON_H2_IR_01"
H2_COMMAND_NAMES = {
    "power_off": "POWER_OFF",
    "mode_auto": "MODE_AUTO",
    "mode_dry": "MODE_DRY",
    "mode_fan_only": "MODE_FAN_ONLY",
    "economy": "ECONOMY",
    "turbo": "TURBO",
    "led_toggle": "LED_TOGGLE",
    "airflow_fix": "AIRFLOW_FIX",
    "swing_toggle": "SWING_TOGGLE",
}
H2_FANS = frozenset({"auto", "low", "medium", "high"})


def h2_request_from_command(command: dict[str, object]) -> dict[str, object]:
    """Map one checked-in Carrier profile command to the Zigbee wire request."""
    command_id = command.get("command_id")
    if not isinstance(command_id, str):
        raise ZigbeeGatewayRequestError("unsupported H2 command")
    if command_id in H2_COMMAND_NAMES:
        return {"command": H2_COMMAND_NAMES[command_id]}
    match = re.fullmatch(r"cool_(1[7-9]|2[0-9]|30)_(auto|low|medium|high)", command_id)
    state = command.get("effective_state")
    if match is None or not isinstance(state, dict):
        raise ZigbeeGatewayRequestError("unsupported H2 command")
    temperature = int(match.group(1))
    fan = match.group(2)
    if (
        state.get("power") is not True or state.get("mode") != "cool"
        or state.get("temperature_c") != temperature or state.get("fan") != fan
        or fan not in H2_FANS
    ):
        raise ZigbeeGatewayRequestError("invalid H2 cooling state")
    return {"command": "COOL_STATE", "temperature_c": temperature, "fan": fan}


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

    def require_h2_device(self, friendly_name: str) -> dict[str, object]: ...

    def send_h2_command(
        self, friendly_name: str, command: dict[str, object]
    ) -> dict[str, object]: ...


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

    def require_h2_device(self, friendly_name: str) -> dict[str, object]:
        del friendly_name
        raise ZigbeeGatewayUnavailableError("Zigbee MQTT bridge is disabled")

    def send_h2_command(
        self, friendly_name: str, command: dict[str, object]
    ) -> dict[str, object]:
        del friendly_name, command
        raise ZigbeeGatewayUnavailableError("Zigbee MQTT bridge is disabled")


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
        self._pending_ir: dict[int, dict[str, object]] = {}
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
            for pending in self._pending_ir.values():
                pending["status"] = "disconnected"
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

    def require_h2_device(self, friendly_name: str) -> dict[str, object]:
        with self._lock:
            if not self._running or not self._connected:
                raise ZigbeeGatewayUnavailableError("Zigbee2MQTT is not connected")
            matches = [
                device for device in self._devices
                if device.get("friendly_name") == friendly_name
                and device.get("model") == H2_IR_MODEL
                and device.get("supported") is True
                and device.get("interview_state") == "SUCCESSFUL"
                and not device.get("interviewing")
            ]
        if len(matches) != 1:
            raise ZigbeeGatewayUnavailableError("supported H2 IR device is not registered")
        if any(character in friendly_name for character in ("/", "+", "#")):
            raise ZigbeeGatewayUnavailableError("invalid H2 MQTT device name")
        return deepcopy(matches[0])

    def send_h2_command(
        self, friendly_name: str, command: dict[str, object]
    ) -> dict[str, object]:
        self.require_h2_device(friendly_name)
        ir_request = h2_request_from_command(command)
        request_id = secrets.randbelow(0xFFFFFF) + 1
        event = Event()
        with self._lock:
            while request_id in self._pending_ir:
                request_id = secrets.randbelow(0xFFFFFF) + 1
            self._pending_ir[request_id] = {
                "event": event, "friendly_name": friendly_name,
                "command": ir_request["command"], "status": None,
            }
        try:
            payload = json.dumps({"ir_request": {**ir_request, "request_id": request_id}},
                                 separators=(",", ":"))
            try:
                result = self._client.publish(
                    f"{self._service.base_topic}/{friendly_name}/set",
                    payload,
                    qos=0,
                    retain=False,
                )
            except Exception as exc:
                raise ZigbeeGatewayRequestError("failed to publish H2 IR command") from exc
            if getattr(result, "rc", mqtt.MQTT_ERR_SUCCESS) != mqtt.MQTT_ERR_SUCCESS:
                raise ZigbeeGatewayRequestError("failed to publish H2 IR command")
            if not event.wait(timeout=18):
                raise ZigbeeGatewayRequestError(
                    "H2 result timed out; IR may have been sent. "
                    "Check the appliance before retrying"
                )
            with self._lock:
                response_status = self._pending_ir[request_id]["status"]
            if response_status != "sent":
                raise ZigbeeGatewayRequestError(f"H2 IR result: {response_status}")
            return {
                "id": uuid.uuid4().hex,
                "transport": "zigbee-h2-ir",
                "status": "sent",
                "command_id": command["command_id"],
                "request_id": request_id,
                "sent_at": _now(),
                "hardware_output": True,
                "appliance_state_confirmed": False,
            }
        finally:
            with self._lock:
                self._pending_ir.pop(request_id, None)

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
            for pending in self._pending_ir.values():
                pending["status"] = "disconnected"
                event = pending["event"]
                if isinstance(event, Event):
                    event.set()
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
        if self._handle_h2_ir_result(
            message.topic, payload_bytes, retained=bool(getattr(message, "retain", False))
        ):
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

    def _handle_h2_ir_result(self, topic: str, payload: bytes, *, retained: bool = False) -> bool:
        with self._lock:
            h2_names = {
                str(device["friendly_name"]) for device in self._devices
                if device.get("model") == H2_IR_MODEL
            }
        if topic not in {f"{self._service.base_topic}/{name}" for name in h2_names}:
            return False
        if retained:
            return True
        try:
            decoded = self._decode_json(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return True
        if not isinstance(decoded, dict):
            return True
        result = decoded.get("ir_result")
        if not isinstance(result, dict):
            return True
        request_id = result.get("request_id")
        status = result.get("status")
        if isinstance(request_id, bool) or not isinstance(request_id, int):
            return True
        if not isinstance(result.get("command"), str) or status not in {
            "sent", "failed", "duplicate", "busy", "accepted",
        }:
            return True
        with self._lock:
            pending = self._pending_ir.get(request_id)
            if (pending is None or topic != f"{self._service.base_topic}/{pending['friendly_name']}"
                or result["command"] != pending["command"]):
                return True
            if status != "accepted":
                pending["status"] = status
                event = pending["event"]
                if isinstance(event, Event):
                    event.set()
            self._last_message_at = _now()
        return True
