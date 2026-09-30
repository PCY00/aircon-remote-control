"""SQLite persistence for automation rules, runtime state, and history."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

DOOR_OPEN_AIRCON_RULE_ID = "door-open-aircon-warning"


class AutomationNotFoundError(LookupError):
    """Raised when an automation rule does not exist."""


def _timestamp(value: datetime | None = None) -> str:
    resolved = value or datetime.now(UTC)
    if resolved.tzinfo is None:
        raise ValueError("automation timestamps must include a timezone")
    return resolved.astimezone(UTC).isoformat()


class AutomationStore:
    """Keep dashboard automation configuration independent from browser storage."""

    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "automations" / "automations.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            connection.row_factory = sqlite3.Row
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS automation_rules (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    delay_seconds INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS automation_state (
                    rule_id TEXT PRIMARY KEY,
                    condition_started_at TEXT,
                    warning_active INTEGER NOT NULL DEFAULT 0,
                    triggered_at TEXT,
                    FOREIGN KEY (rule_id) REFERENCES automation_rules(id)
                );

                CREATE TABLE IF NOT EXISTS automation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    FOREIGN KEY (rule_id) REFERENCES automation_rules(id)
                );

                CREATE INDEX IF NOT EXISTS idx_automation_events_time
                    ON automation_events(occurred_at DESC, id DESC);
                """
            )
            now = _timestamp()
            connection.execute(
                """
                INSERT OR IGNORE INTO automation_rules (
                    id, kind, name, enabled, delay_seconds, created_at, updated_at
                ) VALUES (?, 'door_open_aircon_warning', ?, 1, 300, ?, ?)
                """,
                (DOOR_OPEN_AIRCON_RULE_ID, "문 열림 냉방 경고", now, now),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO automation_state (
                    rule_id, condition_started_at, warning_active, triggered_at
                ) VALUES (?, NULL, 0, NULL)
                """,
                (DOOR_OPEN_AIRCON_RULE_ID,),
            )

    @staticmethod
    def _rule_from_row(row: sqlite3.Row) -> dict[str, object]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "delay_seconds": row["delay_seconds"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _state_from_row(row: sqlite3.Row) -> dict[str, object]:
        return {
            "condition_started_at": row["condition_started_at"],
            "warning_active": bool(row["warning_active"]),
            "triggered_at": row["triggered_at"],
        }

    def list_rules(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM automation_rules ORDER BY created_at, id"
            ).fetchall()
        return [self._rule_from_row(row) for row in rows]

    def get_rule(self, rule_id: str) -> dict[str, object]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM automation_rules WHERE id = ?", (rule_id,)
            ).fetchone()
        if row is None:
            raise AutomationNotFoundError(rule_id)
        return self._rule_from_row(row)

    def update_rule(
        self,
        rule_id: str,
        *,
        enabled: bool | None,
        delay_seconds: int | None,
        updated_at: datetime,
    ) -> dict[str, object]:
        rule = self.get_rule(rule_id)
        next_enabled = bool(rule["enabled"]) if enabled is None else enabled
        next_delay = int(rule["delay_seconds"]) if delay_seconds is None else delay_seconds
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE automation_rules
                SET enabled = ?, delay_seconds = ?, updated_at = ?
                WHERE id = ?
                """,
                (int(next_enabled), next_delay, _timestamp(updated_at), rule_id),
            )
            if not next_enabled:
                connection.execute(
                    """
                    UPDATE automation_state
                    SET condition_started_at = NULL,
                        warning_active = 0,
                        triggered_at = NULL
                    WHERE rule_id = ?
                    """,
                    (rule_id,),
                )
        return self.get_rule(rule_id)

    def get_state(self, rule_id: str) -> dict[str, object]:
        self.get_rule(rule_id)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM automation_state WHERE rule_id = ?", (rule_id,)
            ).fetchone()
        if row is None:
            raise AutomationNotFoundError(rule_id)
        return self._state_from_row(row)

    def set_state(
        self,
        rule_id: str,
        *,
        condition_started_at: datetime | None,
        warning_active: bool,
        triggered_at: datetime | None,
    ) -> dict[str, object]:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE automation_state
                SET condition_started_at = ?, warning_active = ?, triggered_at = ?
                WHERE rule_id = ?
                """,
                (
                    _timestamp(condition_started_at)
                    if condition_started_at is not None
                    else None,
                    int(warning_active),
                    _timestamp(triggered_at) if triggered_at is not None else None,
                    rule_id,
                ),
            )
        return self.get_state(rule_id)

    def record_event(
        self,
        rule_id: str,
        *,
        event_type: str,
        message: str,
        occurred_at: datetime,
        snapshot: dict[str, object],
    ) -> dict[str, object]:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO automation_events (
                    rule_id, event_type, message, occurred_at, snapshot_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rule_id,
                    event_type,
                    message,
                    _timestamp(occurred_at),
                    json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            event_id = cursor.lastrowid
        return {
            "id": event_id,
            "rule_id": rule_id,
            "event_type": event_type,
            "message": message,
            "occurred_at": _timestamp(occurred_at),
            "snapshot": snapshot,
        }

    def list_events(self, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, rule_id, event_type, message, occurred_at, snapshot_json
                FROM automation_events
                ORDER BY occurred_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "rule_id": row["rule_id"],
                "event_type": row["event_type"],
                "message": row["message"],
                "occurred_at": row["occurred_at"],
                "snapshot": json.loads(row["snapshot_json"]),
            }
            for row in rows
        ]
