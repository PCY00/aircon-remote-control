import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.sensors.service import (
    InvalidSensorMessageError,
    SensorService,
    UnsupportedSensorMessageError,
)
from app.sensors.store import SensorStore


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self.value
        self.value += timedelta(seconds=1)
        return current


def ingest(service: SensorService, device_id: str, payload: dict[str, object]) -> dict[str, object]:
    return service.ingest_mqtt(
        f"zigbee2mqtt/{device_id}",
        json.dumps(payload).encode(),
    )


def test_door_state_is_persisted_and_only_transitions_become_events(tmp_path: Path) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())

    first = ingest(service, "sensor_door_01", {"contact": True, "battery": 100})
    repeated = ingest(service, "sensor_door_01", {"contact": True, "linkquality": 182})
    opened = ingest(service, "sensor_door_01", {"contact": False})
    closed = ingest(service, "sensor_door_01", {"contact": True})

    assert first["state"]["door_state"] == "closed"
    assert first["event_recorded"] is False
    assert first["last_changed_at"] is None
    assert repeated["event_recorded"] is False
    assert repeated["last_changed_at"] is None
    assert opened["event_recorded"] is True
    assert opened["last_changed_at"] == "2026-09-07T12:00:02+00:00"
    assert closed["event_recorded"] is True
    assert closed["last_changed_at"] == "2026-09-07T12:00:03+00:00"
    assert closed["state"] == {
        "contact": True,
        "door_state": "closed",
        "battery_percent": 100,
        "linkquality": 182,
    }

    events = service.list_events("sensor_door_01")
    assert [event["state"] for event in events] == ["closed", "open"]
    assert events[0]["previous_state"] == "open"
    assert events[1]["previous_state"] == "closed"


def test_legacy_first_observation_timestamp_is_cleared_without_deleting_state(
    tmp_path: Path,
) -> None:
    store = SensorStore(tmp_path)
    service = SensorService(store=store, clock=Clock())
    original = ingest(service, "sensor_door_01", {"contact": True, "battery": 100})

    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            UPDATE sensor_states
            SET last_changed_at = ?
            WHERE device_id = ?
            """,
            ("2026-09-07T03:22:46.945000+00:00", "sensor_door_01"),
        )

    migrated = SensorStore(tmp_path).get("sensor_door_01")

    assert migrated["last_changed_at"] is None
    assert migrated["first_seen_at"] == original["first_seen_at"]
    assert migrated["state"] == original["state"]


def test_real_door_transition_timestamp_survives_store_initialization(tmp_path: Path) -> None:
    store = SensorStore(tmp_path)
    service = SensorService(store=store, clock=Clock())
    ingest(service, "sensor_door_01", {"contact": True})
    changed = ingest(service, "sensor_door_01", {"contact": False})

    restored = SensorStore(tmp_path).get("sensor_door_01")

    assert restored["last_changed_at"] == changed["last_changed_at"]
    assert len(SensorStore(tmp_path).list_door_events("sensor_door_01")) == 1


def test_sensor_state_survives_a_new_store_instance(tmp_path: Path) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())
    ingest(service, "sensor_door_01", {"contact": False, "battery": 88})

    restored = SensorService(store=SensorStore(tmp_path)).get("sensor_door_01")

    assert restored["kind"] == "door_contact"
    assert restored["state"]["door_state"] == "open"
    assert restored["state"]["battery_percent"] == 88


def test_partial_battery_report_keeps_previous_sensor_kind_and_state(tmp_path: Path) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())
    ingest(service, "sensor_door_01", {"contact": True})

    state = ingest(service, "sensor_door_01", {"battery": 76})

    assert state["kind"] == "door_contact"
    assert state["state"] == {
        "contact": True,
        "door_state": "closed",
        "battery_percent": 76,
    }
    assert service.list_events("sensor_door_01") == []


def test_temperature_humidity_and_source_timestamp_are_normalized(tmp_path: Path) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())

    state = ingest(
        service,
        "sensor_temperature_01",
        {
            "temperature": 25.59,
            "humidity": 39.73,
            "battery": 100,
            "voltage": 3000,
            "last_seen": "2026-09-07T20:59:10+09:00",
        },
    )

    assert state["kind"] == "temperature_humidity"
    assert state["state"]["temperature_c"] == 25.59
    assert state["state"]["humidity_percent"] == 39.73
    assert state["last_reported_at"] == "2026-09-07T11:59:10+00:00"
    assert state["last_received_at"] == "2026-09-07T12:00:00+00:00"


@pytest.mark.parametrize(
    ("topic", "payload", "error_type"),
    [
        ("other/sensor_door_01", b"{}", InvalidSensorMessageError),
        ("zigbee2mqtt/bridge/state", b"{}", InvalidSensorMessageError),
        ("zigbee2mqtt/Sensor Door", b"{}", InvalidSensorMessageError),
        ("zigbee2mqtt/sensor_door_01", b"not-json", InvalidSensorMessageError),
        ("zigbee2mqtt/sensor_door_01", b"[]", InvalidSensorMessageError),
        ("zigbee2mqtt/sensor_door_01", b'{"noise":1}', UnsupportedSensorMessageError),
    ],
)
def test_invalid_or_unsupported_messages_are_rejected(
    tmp_path: Path,
    topic: str,
    payload: bytes,
    error_type: type[Exception],
) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())

    with pytest.raises(error_type):
        service.ingest_mqtt(topic, payload)


def test_oversized_payload_is_rejected(tmp_path: Path) -> None:
    service = SensorService(store=SensorStore(tmp_path), max_payload_bytes=10)

    with pytest.raises(InvalidSensorMessageError, match="size limit"):
        service.ingest_mqtt("zigbee2mqtt/sensor_door_01", b"x" * 11)


def test_older_report_cannot_roll_back_door_state_or_add_events(tmp_path: Path) -> None:
    clock = Clock()
    service = SensorService(store=SensorStore(tmp_path), clock=clock)
    ingest(service, "sensor_door_01", {
        "contact": True, "last_seen": "2026-09-07T11:58:00+00:00",
    })
    latest = ingest(service, "sensor_door_01", {
        "contact": False, "battery": 90, "last_seen": "2026-09-07T11:59:00.100000+00:00",
    })
    # Reconnect/restart must preserve the source timestamp used for ordering.
    restarted = SensorService(store=SensorStore(tmp_path), clock=clock)
    stale = ingest(restarted, "sensor_door_01", {
        "contact": True, "battery": 100, "last_seen": "2026-09-07T20:59:00+09:00",
    })

    assert stale["state"] == latest["state"]
    assert stale["source_timestamp"] == latest["source_timestamp"]
    assert stale["last_reported_at"] == latest["last_reported_at"]
    assert stale["last_changed_at"] == latest["last_changed_at"]
    assert stale["last_received_at"] > latest["last_received_at"]
    assert stale["event_recorded"] is False
    assert stale["stale_report_ignored"] is True
    assert [item["state"] for item in restarted.list_events("sensor_door_01")] == ["open"]


@pytest.mark.parametrize("source_time", [None, "2026-09-07T11:59:00+00:00"])
def test_equal_or_missing_source_time_does_not_discard_real_transitions(
    tmp_path: Path, source_time: str | None
) -> None:
    service = SensorService(store=SensorStore(tmp_path), clock=Clock())
    ingest(service, "sensor_door_01", {
        "contact": True, "last_seen": "2026-09-07T11:59:00+00:00",
    })
    changed = ingest(service, "sensor_door_01", {
        "contact": False, "last_seen": source_time,
    })

    assert changed["state"]["door_state"] == "open"
    assert changed["event_recorded"] is True


def test_metadata_update_notifies_live_clients_without_new_sensor_report(tmp_path: Path) -> None:
    updates: list[dict[str, object]] = []
    service = SensorService(store=SensorStore(tmp_path), clock=Clock(), on_update=updates.append)
    original = ingest(service, "sensor_door_01", {"contact": True})
    updates.clear()

    updated = service.update_metadata(
        "sensor_door_01", display_name="현관문", room="현관", icon="door-open"
    )

    assert updates == [updated]
    assert updated["metadata"]["display_name"] == "현관문"
    assert updated["last_received_at"] == original["last_received_at"]
    assert service.list_events("sensor_door_01") == []
