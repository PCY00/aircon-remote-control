"""Evaluate persistent smart-home automation rules."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from threading import RLock

from app.automations.store import DOOR_OPEN_AIRCON_RULE_ID, AutomationStore
from app.devices.service import DeviceService
from app.events import EventHub
from app.sensors.service import SensorService


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else None


class AutomationService:
    """Run the first safety rule and expose its current condition."""

    def __init__(
        self,
        *,
        store: AutomationStore,
        sensors: SensorService,
        devices: DeviceService,
        events: EventHub,
        clock: Callable[[], datetime] = _utc_now,
        poll_seconds: float = 5.0,
    ) -> None:
        self._store = store
        self._sensors = sensors
        self._devices = devices
        self._events = events
        self._clock = clock
        self._poll_seconds = poll_seconds
        self._lock = RLock()
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    def _snapshot(self) -> dict[str, object]:
        open_doors = [
            {
                "device_id": sensor["device_id"],
                "name": (sensor.get("metadata") or {}).get("display_name")
                or sensor["device_id"],
            }
            for sensor in self._sensors.list()
            if sensor.get("kind") == "door_contact"
            and (sensor.get("state") or {}).get("door_state") == "open"
        ]
        active_aircons = []
        for device in self._devices.list():
            desired_state = device.get("last_desired_state")
            if (
                str(device.get("profile_id", "")).startswith("air_conditioner/")
                and isinstance(desired_state, dict)
                and desired_state.get("power") is True
            ):
                active_aircons.append(
                    {"device_id": device["id"], "name": device.get("name") or device["id"]}
                )
        return {
            "active": bool(open_doors and active_aircons),
            "open_doors": open_doors,
            "active_air_conditioners": active_aircons,
        }

    def evaluate(self, *, now: datetime | None = None) -> dict[str, object]:
        with self._lock:
            evaluated_at = now or self._clock()
            if evaluated_at.tzinfo is None:
                raise ValueError("automation clock must return a timezone-aware datetime")
            evaluated_at = evaluated_at.astimezone(UTC)
            rule = self._store.get_rule(DOOR_OPEN_AIRCON_RULE_ID)
            state = self._store.get_state(DOOR_OPEN_AIRCON_RULE_ID)
            snapshot = self._snapshot()

            if not rule["enabled"]:
                state = self._store.set_state(
                    DOOR_OPEN_AIRCON_RULE_ID,
                    condition_started_at=None,
                    warning_active=False,
                    triggered_at=None,
                )
            elif snapshot["active"]:
                started_at = _parse_timestamp(state.get("condition_started_at"))
                if started_at is None:
                    started_at = evaluated_at
                    state = self._store.set_state(
                        DOOR_OPEN_AIRCON_RULE_ID,
                        condition_started_at=started_at,
                        warning_active=False,
                        triggered_at=None,
                    )
                elapsed = (evaluated_at - started_at).total_seconds()
                if elapsed >= int(rule["delay_seconds"]) and not state["warning_active"]:
                    message = "문이 열린 채 에어컨이 켜져 있어요."
                    event = self._store.record_event(
                        DOOR_OPEN_AIRCON_RULE_ID,
                        event_type="warning_triggered",
                        message=message,
                        occurred_at=evaluated_at,
                        snapshot=snapshot,
                    )
                    state = self._store.set_state(
                        DOOR_OPEN_AIRCON_RULE_ID,
                        condition_started_at=started_at,
                        warning_active=True,
                        triggered_at=evaluated_at,
                    )
                    self._events.publish(
                        "automation.warning",
                        {"rule_id": rule["id"], "message": message, "event": event},
                    )
            else:
                if state["warning_active"]:
                    message = "문 열림 냉방 경고가 해제됐어요."
                    event = self._store.record_event(
                        DOOR_OPEN_AIRCON_RULE_ID,
                        event_type="warning_resolved",
                        message=message,
                        occurred_at=evaluated_at,
                        snapshot=snapshot,
                    )
                    self._events.publish(
                        "automation.resolved",
                        {"rule_id": rule["id"], "message": message, "event": event},
                    )
                state = self._store.set_state(
                    DOOR_OPEN_AIRCON_RULE_ID,
                    condition_started_at=None,
                    warning_active=False,
                    triggered_at=None,
                )

            return {
                **rule,
                "state": state,
                "condition": snapshot,
                "evaluated_at": evaluated_at.isoformat(),
            }

    def list_rules(self) -> list[dict[str, object]]:
        return [self.evaluate()]

    def update_rule(
        self,
        rule_id: str,
        *,
        enabled: bool | None,
        delay_seconds: int | None,
    ) -> dict[str, object]:
        with self._lock:
            self._store.update_rule(
                rule_id,
                enabled=enabled,
                delay_seconds=delay_seconds,
                updated_at=self._clock(),
            )
            result = self.evaluate()
            self._events.publish("automation.updated", {"rule": result})
            return result

    def list_events(self, limit: int = 50) -> list[dict[str, object]]:
        return self._store.list_events(limit)

    def notify_state_changed(self, _: dict[str, object]) -> None:
        self.evaluate()

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await asyncio.to_thread(self.evaluate)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_seconds
                )
            except TimeoutError:
                continue

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None or self._stop_event is None:
            return
        self._stop_event.set()
        await self._task
        self._task = None
        self._stop_event = None
