"""Application service for registration and semantic device control."""

from __future__ import annotations

import logging
from collections.abc import Callable
from threading import RLock

from app.devices.catalog import DeviceProfileCatalog
from app.devices.commands import DeviceCommandResolver
from app.devices.store import RegisteredDeviceStore
from app.devices.transport import DeviceTransport

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
        on_update: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self._catalog = catalog
        self._store = store
        self._resolver = resolver
        self._transport = transport
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
    ) -> dict[str, object]:
        self._catalog.get(profile_id)
        return self._store.create(name=name, room=room, profile_id=profile_id, icon=icon)

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
