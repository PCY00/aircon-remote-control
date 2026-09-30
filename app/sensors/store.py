"""SQLite persistence for current sensor state and door transitions."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.sensors.models import SensorUpdate


class SensorNotFoundError(LookupError):
    """Raised when a requested sensor has never reported."""


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("sensor timestamps must include a timezone")
    return value.astimezone(UTC).isoformat()


class SensorStore:
    """Persist last-known state, display metadata, and door transition events."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "sensors" / "sensors.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sensor_states (
                    device_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_reported_at TEXT NOT NULL,
                    last_received_at TEXT NOT NULL,
                    source_timestamp TEXT,
                    last_changed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS door_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    previous_state TEXT NOT NULL,
                    state TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    source_timestamp TEXT,
                    FOREIGN KEY (device_id) REFERENCES sensor_states(device_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_door_events_device_time
                    ON door_events(device_id, occurred_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS sensor_metadata (
                    device_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    room TEXT NOT NULL,
                    icon TEXT NOT NULL,
                    customized INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                """
                UPDATE sensor_states
                SET last_changed_at = NULL
                WHERE kind = 'door_contact'
                  AND last_changed_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM door_events
                      WHERE door_events.device_id = sensor_states.device_id
                  )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO sensor_metadata (
                    device_id, display_name, room, icon, customized, updated_at
                )
                SELECT
                    device_id,
                    CASE kind
                        WHEN 'door_contact' THEN '문 열림 센서'
                        WHEN 'temperature_humidity' THEN '온·습도 센서'
                        ELSE device_id
                    END,
                    '공간 미지정',
                    CASE kind
                        WHEN 'door_contact' THEN 'door-open'
                        WHEN 'temperature_humidity' THEN 'thermometer-sun'
                        ELSE 'activity'
                    END,
                    0,
                    first_seen_at
                FROM sensor_states
                """
            )

    @staticmethod
    def _state_from_row(row: sqlite3.Row) -> dict[str, object]:
        available_columns = set(row.keys())
        result: dict[str, object] = {
            "device_id": row["device_id"],
            "kind": row["kind"],
            "state": json.loads(row["state_json"]),
            "first_seen_at": row["first_seen_at"],
            "last_reported_at": row["last_reported_at"],
            "last_received_at": row["last_received_at"],
            "source_timestamp": row["source_timestamp"],
            "last_changed_at": row["last_changed_at"],
        }
        if (
            "metadata_display_name" in available_columns
            and row["metadata_display_name"] is not None
        ):
            result["metadata"] = {
                "display_name": row["metadata_display_name"],
                "room": row["metadata_room"],
                "icon": row["metadata_icon"],
                "customized": bool(row["metadata_customized"]),
                "updated_at": row["metadata_updated_at"],
            }
        else:
            result["metadata"] = None
        return result

    @staticmethod
    def _state_query(where: str = "") -> str:
        return f"""
            SELECT
                sensor_states.*,
                sensor_metadata.display_name AS metadata_display_name,
                sensor_metadata.room AS metadata_room,
                sensor_metadata.icon AS metadata_icon,
                sensor_metadata.customized AS metadata_customized,
                sensor_metadata.updated_at AS metadata_updated_at
            FROM sensor_states
            LEFT JOIN sensor_metadata USING (device_id)
            {where}
        """

    def get_optional(self, device_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._state_query("WHERE sensor_states.device_id = ?"),
                (device_id,),
            ).fetchone()
        return self._state_from_row(row) if row is not None else None

    def get(self, device_id: str) -> dict[str, object]:
        state = self.get_optional(device_id)
        if state is None:
            raise SensorNotFoundError(device_id)
        return state

    def list(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                self._state_query("ORDER BY sensor_states.device_id")
            ).fetchall()
        return [self._state_from_row(row) for row in rows]

    def apply(self, update: SensorUpdate) -> dict[str, object]:
        received_at = _timestamp(update.received_at)
        source_timestamp = (
            _timestamp(update.source_timestamp) if update.source_timestamp is not None else None
        )
        reported_at = source_timestamp or received_at
        raw_json = json.dumps(update.raw_payload, ensure_ascii=False, separators=(",", ":"))

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_row = connection.execute(
                "SELECT * FROM sensor_states WHERE device_id = ?",
                (update.device_id,),
            ).fetchone()
            previous = self._state_from_row(previous_row) if previous_row is not None else None
            previous_source = previous.get("source_timestamp") if previous else None
            if (
                update.source_timestamp is not None
                and isinstance(previous_source, str)
                and update.source_timestamp < datetime.fromisoformat(previous_source)
            ):
                # Replayed or delayed reports must not roll back the current
                # state or invent another door transition. Record their receipt
                # without replacing the newest source report and its timestamp.
                connection.execute(
                    "UPDATE sensor_states SET last_received_at = ? WHERE device_id = ?",
                    (received_at, update.device_id),
                )
                row = connection.execute(
                    self._state_query("WHERE sensor_states.device_id = ?"),
                    (update.device_id,),
                ).fetchone()
                result = self._state_from_row(row)
                result["event_recorded"] = False
                result["stale_report_ignored"] = True
                return result
            previous_state = dict(previous["state"]) if previous is not None else {}
            merged_state = {**previous_state, **update.changes}

            current_door_state = merged_state.get("door_state")
            previous_door_state = previous_state.get("door_state")
            door_changed = (
                isinstance(previous_door_state, str)
                and isinstance(current_door_state, str)
                and previous_door_state != current_door_state
            )
            if door_changed:
                last_changed_at = reported_at
            elif previous is not None:
                last_changed_at = previous.get("last_changed_at")
            else:
                last_changed_at = None

            first_seen_at = (
                str(previous["first_seen_at"]) if previous is not None else received_at
            )
            connection.execute(
                """
                INSERT INTO sensor_states (
                    device_id, kind, state_json, raw_json, first_seen_at,
                    last_reported_at, last_received_at, source_timestamp, last_changed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    kind = excluded.kind,
                    state_json = excluded.state_json,
                    raw_json = excluded.raw_json,
                    last_reported_at = excluded.last_reported_at,
                    last_received_at = excluded.last_received_at,
                    source_timestamp = excluded.source_timestamp,
                    last_changed_at = excluded.last_changed_at
                """,
                (
                    update.device_id,
                    update.kind,
                    json.dumps(merged_state, ensure_ascii=False, separators=(",", ":")),
                    raw_json,
                    first_seen_at,
                    reported_at,
                    received_at,
                    source_timestamp,
                    last_changed_at,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO sensor_metadata (
                    device_id, display_name, room, icon, customized, updated_at
                ) VALUES (?, ?, '공간 미지정', ?, 0, ?)
                """,
                (
                    update.device_id,
                    (
                        "문 열림 센서"
                        if update.kind == "door_contact"
                        else "온·습도 센서"
                        if update.kind == "temperature_humidity"
                        else update.device_id
                    ),
                    (
                        "door-open"
                        if update.kind == "door_contact"
                        else "thermometer-sun"
                        if update.kind == "temperature_humidity"
                        else "activity"
                    ),
                    first_seen_at,
                ),
            )
            event_id: int | None = None
            if door_changed:
                cursor = connection.execute(
                    """
                    INSERT INTO door_events (
                        device_id, previous_state, state, occurred_at,
                        received_at, source_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        update.device_id,
                        previous_door_state,
                        current_door_state,
                        reported_at,
                        received_at,
                        source_timestamp,
                    ),
                )
                event_id = cursor.lastrowid

            row = connection.execute(
                self._state_query("WHERE sensor_states.device_id = ?"),
                (update.device_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("sensor state disappeared after upsert")
        result = self._state_from_row(row)
        result["event_recorded"] = event_id is not None
        if event_id is not None:
            result["event_id"] = event_id
        return result

    def set_metadata(
        self,
        device_id: str,
        *,
        display_name: str,
        room: str,
        icon: str,
        updated_at: datetime,
    ) -> dict[str, object]:
        """Store user-facing sensor settings independently from browser storage."""

        self.get(device_id)
        timestamp = _timestamp(updated_at)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sensor_metadata (
                    device_id, display_name, room, icon, customized, updated_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    room = excluded.room,
                    icon = excluded.icon,
                    customized = 1,
                    updated_at = excluded.updated_at
                """,
                (device_id, display_name, room, icon, timestamp),
            )
        return self.get(device_id)

    def list_door_events(self, device_id: str, limit: int = 50) -> list[dict[str, object]]:
        self.get(device_id)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, device_id, previous_state, state, occurred_at,
                       received_at, source_timestamp
                FROM door_events
                WHERE device_id = ?
                ORDER BY occurred_at DESC, id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]
