"""Application service for registration and semantic device control."""

from __future__ import annotations

import logging
from collections.abc import Callable
from threading import RLock

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.store import RegisteredDeviceStore
from app.devices.transport import DeviceTransport
from app.integrations.mqtt import H2_IR_MODEL, SensorBridge, ZigbeeGatewayUnavailableError

H2_AIRCON_PROFILE = "air_conditioner/Carrier/CS-A061GS"

LOGGER = logging.getLogger(__name__)


class DeviceService:
    """Coordinate catalog lookup, persistence, command resolution, and transport."""

    def __init__(
        self,
        *,
        catalog: DeviceProfileCatalog,
        store: RegisteredDeviceStore,
        resolver: DeviceCommandResolver,
        transport: DeviceTransport,
        zigbee_bridge: SensorBridge | None = None,
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._catalog = catalog
        self._store = store
        self._resolver = resolver
        self._transport = transport
        self._zigbee_bridge = zigbee_bridge
        self._command_lock = RLock()
        self._listeners: list[Callable[[dict[str, object]], None]] = []
        if on_update is not None:
            self._listeners.append(on_update)

    def add_listener(self, listener: Callable[[dict[str, object]], None]) -> None:
        self._listeners.append(listener)

    def _notify(self, result: dict[str, object]) -> None:
        for listener in tuple(self._listeners):
            try:
                listener(result)
            except Exception:
                LOGGER.exception("device update listener failed")

    def register(
        self,
        *,
        name: str,
        room: str,
        profile_id: str,
        icon: str = "box",
        zigbee_friendly_name: str | None = None,
    ) -> dict[str, object]:
        self._catalog.get(profile_id)
        with self._command_lock:
            binding = self._validate_h2_binding(profile_id, zigbee_friendly_name)
            return self._store.create(
                name=name, room=room, profile_id=profile_id, icon=icon,
                zigbee_binding=binding,
            )

    def _validate_h2_binding(
        self, profile_id: str, friendly_name: str | None, device_id: str | None = None
    ) -> dict[str, str] | None:
        if friendly_name is None:
            return None
        if profile_id != H2_AIRCON_PROFILE:
            raise ValueError("H2 IR currently supports only Carrier CS-A061GS")
        if self._zigbee_bridge is None:
            raise ZigbeeGatewayUnavailableError("Zigbee bridge is unavailable")
        self._zigbee_bridge.require_h2_device(friendly_name)
        for other in self._store.list():
            if other.get("id") == device_id:
                continue
            binding = other.get("zigbee_binding")
            if isinstance(binding, dict) and binding.get("friendly_name") == friendly_name:
                raise ValueError("H2 IR device is already linked to another air conditioner")
        return {"type": "h2_ir", "model": H2_IR_MODEL, "friendly_name": friendly_name}

    def bind_h2(self, device_id: str, friendly_name: str) -> dict[str, object]:
        with self._command_lock:
            device = self._store.get(device_id)
            binding = self._validate_h2_binding(
                str(device["profile_id"]), friendly_name, device_id
            )
            return self._store.set_zigbee_binding(device_id, binding)

    def unbind_h2(self, device_id: str) -> dict[str, object]:
        with self._command_lock:
            self._store.get(device_id)
            return self._store.set_zigbee_binding(device_id, None)

    def list(self) -> list[dict[str, object]]:
        return self._store.list()

    def execute(self, device_id: str, request: dict[str, object]) -> dict[str, object]:
        # Keep persistence and notifications in the same order as physical sends.
        # The transport's own send lock alone cannot prevent a later command's
        # state from being overwritten by an earlier request still saving.
        with self._command_lock:
            device = self._store.get(device_id)
            profile_id = str(device["profile_id"])
            command = self._resolver.resolve(profile_id, request)
            binding = device.get("zigbee_binding")
            if isinstance(binding, dict) and binding.get("type") == "h2_ir":
                if self._zigbee_bridge is None:
                    raise ZigbeeGatewayUnavailableError("Zigbee bridge is unavailable")
                transmission = self._zigbee_bridge.send_h2_command(
                    str(binding["friendly_name"]), command
                )
            else:
                transmission = self._transport.send(
                    device_id=device_id,
                    profile_id=profile_id,
                    command=command,
                )
            effective_state = command.get("effective_state")
            updated_device = self._store.record_command(
                device_id,
                command_id=str(command["command_id"]),
                command_kind=str(command.get("kind", "unknown")),
                effective_state=effective_state if isinstance(effective_state, dict) else None,
            )
            result = {
                "device": updated_device,
                "resolved_command": command,
                "transmission": transmission,
            }
            self._notify(result)
            return result
