"""Initialize owned runtime metadata without replacing existing data."""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from central_server.schema import STATEMENTS
from central_server.push_schema import PUSH_STATEMENTS

SCHEMA_VERSION = 3


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(path, timeout=5)) as connection, connection:
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if (version not in (0, 1, 2, SCHEMA_VERSION) or (version == 0 and tables)
                or (version == 1 and tables != {'runtime_metadata'})):
            raise RuntimeError('Unrecognized existing database; preserve and inspect.')
        base = {'runtime_metadata', 'users', 'homes', 'audit', 'memberships', 'invitations', 'hubs', 'events'}
        expected = base if version == 2 else base | {'installations', 'push_messages', 'push_jobs'}
        if version in (2, 3) and tables != expected:
            raise RuntimeError('Unrecognized existing database; preserve and inspect.')
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('BEGIN IMMEDIATE')
        if version == 0:
            connection.execute('CREATE TABLE runtime_metadata '
                               '(id INTEGER PRIMARY KEY CHECK(id=1), '
                               'installation_id TEXT NOT NULL, created_at TEXT NOT NULL)')
            connection.execute('INSERT INTO runtime_metadata VALUES (1, ?, ?)',
                               (str(uuid.uuid4()), datetime.now(UTC).isoformat()))
        if version in (0, 1):
            for statement in STATEMENTS:
                connection.execute(statement)
        if version in (0, 1, 2):
            for statement in PUSH_STATEMENTS:
                connection.execute(statement)
            connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        if not connection.execute('SELECT 1 FROM runtime_metadata WHERE id=1').fetchone():
            raise RuntimeError('Runtime metadata missing; preserve and inspect.')
    path.chmod(0o600)


def ready(path: Path) -> bool:
    # Read-only URI prevents a health request creating an empty replacement database.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as conn:
        return (conn.execute('PRAGMA user_version').fetchone()[0] == SCHEMA_VERSION
                and conn.execute('SELECT 1 FROM runtime_metadata WHERE id=1').fetchone() == (1,))
