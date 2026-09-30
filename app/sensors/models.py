"""Domain models shared by sensor ingestion and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SensorUpdate:
    """One validated, normalized sensor report."""

    device_id: str
    kind: str
    changes: dict[str, object]
    raw_payload: dict[str, object]
    received_at: datetime
    source_timestamp: datetime | None = None

