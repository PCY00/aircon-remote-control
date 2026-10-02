"""Source preservation, durable cursors, bounded relay and authenticated HTTPS contracts."""

import importlib.util
import json
import sqlite3
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_central_push import setup as setup

spec = importlib.util.spec_from_file_location(
    "pi_central_agent", Path(__file__).parents[1] / "services/pi-central-agent/agent.py"
)
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


@pytest.fixture
def sources(tmp_path):
    directory = tmp_path / "runtime"
    for source, (relative, _table) in agent.SOURCES.items():
        path = directory / relative
        path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as conn:
            if source == "door":
                conn.execute(
                    "CREATE TABLE door_events(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "device_id TEXT,previous_state TEXT,state TEXT,occurred_at TEXT)"
                )
            else:
                conn.execute(
                    "CREATE TABLE automation_events(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "event_type TEXT,occurred_at TEXT,snapshot_json TEXT)"
                )
    clock = [1000.0]
    store = agent.Store(tmp_path / "agent/outbox.sqlite3", clock=lambda: clock[0])
    return directory, store, clock


def add(directory, source="door", at=1000.0):
    relative, table = agent.SOURCES[source]
    occurred = datetime.fromtimestamp(at, UTC).isoformat()
    with sqlite3.connect(directory / relative) as conn:
        if source == "door":
            conn.execute(
                "INSERT INTO door_events VALUES(NULL,?,?,?,?)",
                ("private-mac", "closed", "open", occurred),
            )
        else:
            conn.execute(
                "INSERT INTO automation_events VALUES(NULL,?,?,?)",
                ("warning_triggered", occurred, '{"private":"room-and-MAC"}'),
            )


def test_first_baseline_skips_history_and_source_bytes_are_preserved(sources):
    directory, store, _ = sources
    add(directory)
    original = {
        name: (directory / relative).read_bytes() for name, (relative, _) in agent.SOURCES.items()
    }
    assert store.collect(directory)["baseline"] == 2
    assert store.next() is None
    assert original == {
        name: (directory / relative).read_bytes() for name, (relative, _) in agent.SOURCES.items()
    }


def test_fresh_door_and_warning_survive_restart_without_private_source_details(sources):
    directory, store, clock = sources
    store.collect(directory)
    add(directory)
    add(directory, "automation")
    assert store.collect(directory)["queued"] == 2
    item = store.next()
    assert "private" not in item["payload"] and "device_id" not in item["payload"]
    assert len(item["event_id"]) == 64
    reopened = agent.Store(store.path, clock=lambda: clock[0])
    assert reopened.next() == item
    assert reopened.collect(directory)["queued"] == 0


def test_expired_sources_and_queue_do_not_replay_old_alerts(sources):
    directory, store, clock = sources
    store.collect(directory)
    add(directory, at=700)
    assert store.collect(directory)["expired"] == 1
    assert store.next() is None
    add(directory)
    store.collect(directory)
    clock[0] = 1240
    assert store.next() is None
    with store.connect() as conn:
        assert conn.execute("SELECT state FROM outbox").fetchone()[0] == "expired"


def test_future_source_is_skipped_once_without_inventing_an_event(sources):
    directory, store, _ = sources
    store.collect(directory)
    add(directory, at=2000)
    assert store.collect(directory)["invalid"] == 1
    assert store.next() is None
    assert store.collect(directory)["invalid"] == 0


def test_reset_source_requires_inspection_and_keeps_existing_cursor(sources):
    directory, store, _ = sources
    add(directory)
    store.collect(directory)
    with sqlite3.connect(directory / agent.SOURCES["door"][0]) as conn:
        conn.execute("DELETE FROM door_events")
    with pytest.raises(agent.SourceChangedError):
        store.collect(directory)
    with store.connect() as conn:
        assert conn.execute("SELECT last_id FROM cursors WHERE source='door'").fetchone()[0] == 1


def test_full_queue_rolls_back_cursor_and_keeps_source_for_later(sources):
    directory, store, _ = sources
    store.collect(directory)
    with store.connect() as conn:
        for index in range(1000):
            store._enqueue(conn, str(index), "fixture", {}, 1240)
    add(directory)
    with pytest.raises(agent.QueueFullError):
        store.collect(directory)
    with store.connect() as conn:
        assert conn.execute("SELECT last_id FROM cursors WHERE source='door'").fetchone()[0] == 0


def test_connection_test_is_distinct_from_sensor_and_retry_body_is_stable(sources):
    _, store, clock = sources
    store.connection_test()
    item = store.next()
    assert item["kind"] == "hub.connection_test"
    store.finish(item, "retry")
    assert store.next() is None
    clock[0] += 10
    later = store.next()
    assert later["event_id"] == item["event_id"] and later["payload"] == item["payload"]
    assert later["attempts"] == 1
    store.finish(later, "accepted")
    assert store.next() is None


@pytest.mark.parametrize(
    "origin",
    [
        "http://example.test",
        "https://user@example.test",
        "https://example.test/path",
        "https://example.test?secret=x",
        "https://example.test:8001",
        "https://example.test/#x",
    ],
)
def test_origin_rejects_http_credentials_paths_and_query(origin):
    with pytest.raises(ValueError):
        agent.endpoint(origin)


def test_http_send_uses_only_hub_auth_and_fixed_endpoint_without_home_injection(sources):
    _, store, _ = sources
    store.connection_test()
    sender = agent.Sender({"endpoint": "https://example.test", "hub_token": "fixture-hub"})
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"id":1,"duplicate":true}'

    class Opener:
        def open(self, request, **kwargs):
            requests.append(request)
            return Response()

    sender.opener = Opener()
    assert sender.send(store.next()) == "accepted"
    assert requests[0].full_url == "https://example.test/v1/hub/events"
    body = json.loads(requests[0].data)
    assert set(body) == {"event_id", "kind", "payload"}
    assert requests[0].get_header("Authorization") == "Bearer fixture-hub"
    assert (
        agent.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test") is None
    )


def test_revoked_hub_stops_further_network_requests(sources):
    _, store, _ = sources
    store.connection_test()
    sender = agent.Sender({"endpoint": "https://example.test", "hub_token": "fixture-hub"})

    class Opener:
        calls = 0

        def open(self, *args, **kwargs):
            self.calls += 1
            raise urllib.error.HTTPError("https://example.test", 401, "private", {}, None)

    sender.opener = Opener()
    assert agent.dispatch(store, sender)
    store.connection_test()
    assert not agent.dispatch(store, sender)
    assert sender.opener.calls == 1


def test_lost_ack_retry_reaches_central_once_with_original_expiry_and_family_only(sources, setup):
    directory, store, clock = sources
    db, now, homes, _, owner, member, outsider, *_, hub = setup
    store.collect(directory)
    add(directory)
    store.collect(directory)
    sender = agent.Sender({"endpoint": "https://example.test", "hub_token": hub["hub_token"]})

    class Reply:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return json.dumps(self.value).encode()

    class LostFirstAck:
        calls = 0

        def open(self, request, **kwargs):
            self.calls += 1
            body = json.loads(request.data)
            response = Reply()
            response.value = homes.ingest(
                hub["hub_token"], body["event_id"], body["kind"], body["payload"]
            )
            if self.calls == 1:
                raise urllib.error.URLError("Simulated acknowledgement loss after commit")
            assert response.value["duplicate"]
            return response

    sender.opener = LostFirstAck()
    assert agent.dispatch(store, sender)
    clock[0] = now[0] = 1060
    assert agent.dispatch(store, sender)
    assert store.next() is None
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert conn.execute("SELECT expires_at FROM push_messages").fetchone()[0] == 1240
        recipients = {row[0] for row in conn.execute("SELECT user_id FROM push_jobs")}
        assert recipients == {owner, member} and outsider not in recipients
