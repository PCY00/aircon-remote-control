import sqlite3
from pathlib import Path

import pytest

from app.automations.store import AutomationStore
from app.sensors.store import SensorStore


@pytest.mark.parametrize("store_type", [SensorStore, AutomationStore])
def test_store_closes_connections_after_success_and_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    store_type: type[SensorStore] | type[AutomationStore],
) -> None:
    connections: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracked_connect(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked_connect)
    store = store_type(tmp_path)
    with store._connect() as connection:
        connection.execute("CREATE TABLE rollback_probe (value TEXT)")
    with pytest.raises(RuntimeError, match="rollback probe"), store._connect() as connection:
        connection.execute("INSERT INTO rollback_probe VALUES ('not committed')")
        raise RuntimeError("rollback probe")
    with store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM rollback_probe").fetchone()[0] == 0

    # Retaining references prevents GC from concealing leaked connections.
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
