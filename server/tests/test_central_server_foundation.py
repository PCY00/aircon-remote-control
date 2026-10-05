"""Protect persistent data, readiness failure, and bounded crash recovery."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'services/central-server'))
from central_server.restart_guard import record_failure
from central_server.storage import initialize, ready
from central_server.web import create_app


def test_repeated_start_preserves_persistent_runtime_identity(tmp_path):
    db = tmp_path/'central.sqlite3'
    initialize(db)
    with sqlite3.connect(db) as connection:
        before = connection.execute('SELECT * FROM runtime_metadata').fetchall()
    initialize(db)
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT * FROM runtime_metadata').fetchall() == before
        assert connection.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert ready(db)


@pytest.mark.parametrize('version', [0, 3])
def test_unrecognized_existing_database_is_preserved(tmp_path, version):
    db = tmp_path/'existing.sqlite3'
    with sqlite3.connect(db) as connection:
        connection.execute('CREATE TABLE owner_data(value TEXT)')
        connection.execute("INSERT INTO owner_data VALUES ('keep')")
        connection.execute(f'PRAGMA user_version={version}')
    with pytest.raises(RuntimeError, match='preserve'):
        initialize(db)
    with sqlite3.connect(db) as connection:
        assert connection.execute('SELECT value FROM owner_data').fetchone() == ('keep',)


def test_readiness_does_not_create_missing_database_or_disclose_paths(tmp_path):
    db = tmp_path/'private-missing.sqlite3'
    client = create_app(db).test_client()
    response = client.get('/health/ready')
    assert response.status_code == 503
    assert response.json == {'status': 'unavailable', 'database': 'unavailable'}
    assert not db.exists()
    assert str(tmp_path) not in response.text
    assert client.get('/health/live').status_code == 200


def test_foundation_does_not_offer_household_or_command_routes(tmp_path):
    db = tmp_path/'central.sqlite3'
    initialize(db)
    client = create_app(db).test_client()
    assert client.get('/health/ready').status_code == 200
    assert client.post('/health/ready', json={'home_id': 'other'}).status_code == 405
    assert client.get('/homes').status_code == 404
    assert client.post('/commands', json={'power': True}).status_code == 404
    assert 'installation_id' not in client.get('/health/live').text


def test_five_crashes_stop_restarts_and_persist_budget(tmp_path):
    state, service = tmp_path/'state', tmp_path/'service'
    service.mkdir()
    for index in range(1, 6):
        assert record_failure(state, service, status=-1, signal=9, now=100+index) == index
    assert (service/'down').exists()
    assert len(json.loads((state/'restart-state.json').read_text())['failures']) == 5


def test_explicit_stop_does_not_count_and_old_crashes_expire(tmp_path):
    state, service = tmp_path/'state', tmp_path/'service'
    service.mkdir()
    assert record_failure(state, service, status=-1, signal=15, now=100) == 0
    assert not (state/'restart-state.json').exists()
    assert record_failure(state, service, status=1, signal=0, now=100) == 1
    assert record_failure(state, service, status=1, signal=0, now=401) == 1
    assert not (service/'down').exists()


def test_corrupt_crash_history_stops_instead_of_resetting_budget(tmp_path):
    state, service = tmp_path/'state', tmp_path/'service'
    state.mkdir()
    service.mkdir()
    (state/'restart-state.json').write_text('invalid json')
    assert record_failure(state, service, status=1, signal=0, now=100) >= 5
    assert (service/'down').exists()
