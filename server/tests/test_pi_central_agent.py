"""Source preservation, durable cursors, bounded relay and authenticated HTTPS contracts."""

import importlib.util
import json
import logging
import re
import sqlite3
import sys
import time
import types
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


def test_event_and_control_requests_identify_the_hub_client():
    """The public edge must see our application name, rather than Python's default UA."""
    calls = []

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, *args): return b'{"id":1,"duplicate":false}'

    class Edge:
        def open(self, request, **kwargs):
            # Both real hub endpoints must retain authentication while naming the client.
            assert request.get_header('User-agent') == 'FamilySmartHome-Pi/0.7.0'
            assert request.get_header('Authorization') == 'Bearer hub_test'
            calls.append(request.full_url)
            return Response()

    sender = agent.Sender({'endpoint':'https://house.example.test','hub_token':'hub_test'})
    sender.opener = Edge()
    assert sender.send({'event_id':'event-1','kind':'door.opened','payload':'{}'}) == 'accepted'
    assert agent.ControlChannel({'endpoint':'https://house.example.test'}, sender).request('/v1/hub/control/next',{}) == {'id':1,'duplicate':False}
    assert calls == ['https://house.example.test/v1/hub/events','https://house.example.test/v1/hub/control/next']


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
    # Only the hashed inventory id travels (0.7.0), never the Zigbee friendly name or a room.
    assert "private" not in item["payload"]
    assert json.loads(item["payload"])["device_id"] == agent.device_ref(store.namespace(),
                                                                        "private-mac")
    assert len(item["event_id"]) == 64
    reopened = agent.Store(store.path, clock=lambda: clock[0])
    assert reopened.next() == item
    assert reopened.collect(directory)["queued"] == 0


def test_latest_climate_reports_baseline_then_emit_new_values_once_without_mac(sources):
    directory, store, clock = sources
    path = directory / "sensors/sensors.sqlite3"

    def report(at, value):
        with sqlite3.connect(path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sensor_states(device_id TEXT PRIMARY KEY,kind TEXT,"
                "state_json TEXT,last_reported_at TEXT)"
            )
            conn.execute(
                "INSERT OR REPLACE INTO sensor_states VALUES(?,?,?,?)",
                (
                    "private-sensor-mac",
                    "temperature_humidity",
                    json.dumps(value),
                    datetime.fromtimestamp(at, UTC).isoformat(),
                ),
            )

    report(1000, {"temperature_c": 24, "humidity_percent": 50, "private": "raw-room"})
    assert store.collect(directory)["climate_baseline"] == 1
    assert store.next() is None
    clock[0] += 1
    report(1001, {"temperature_c": 25, "humidity_percent": 51, "private": "raw-room"})
    assert store.collect(directory)["climate_queued"] == 1
    item = store.next()
    assert item["kind"] == "sensor.climate_report" and "private" not in item["payload"]
    assert json.loads(item["payload"])["temperature_c"] == 25
    store = agent.Store(store.path, clock=lambda: clock[0])
    assert store.collect(directory)["climate_queued"] == 0
    clock[0] += 1
    report(1002, {"temperature_c": True, "humidity_percent": 150})
    assert store.collect(directory)["climate_invalid"] == 1
    assert store.next() == item


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


class Stop(BaseException):
    pass


def run_agent(monkeypatch, tmp_path, directory, control, poll):
    config = {
        "endpoint": "https://example.test",
        "hub_token": "hub_" + "x" * 43,
        "source_data_dir": str(directory),
    }
    if control:
        config["control_origin"] = "http://127.0.0.1:8001"
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 8:
            raise Stop

    monkeypatch.setitem(
        sys.modules, "fcntl", types.SimpleNamespace(flock=lambda *a: None, LOCK_EX=2, LOCK_NB=4)
    )
    monkeypatch.setattr(agent, "RotatingFileHandler", lambda *a, **k: logging.NullHandler())
    monkeypatch.setattr(agent, "LOGGED", {})
    monkeypatch.setattr(agent, "load_config", lambda path: config)
    monkeypatch.setattr(agent, "poll_control", poll)
    monkeypatch.setattr(agent.time, "sleep", sleep)
    monkeypatch.setattr(
        sys, "argv", ["agent", "--config", str(tmp_path / "c.json"), "--state", str(tmp_path / "s")]
    )
    agent.main()


@pytest.mark.parametrize("failure", ["missing", "changed", "schema"])
@pytest.mark.parametrize("control", [True, False])
def test_source_failure_keeps_control_polling_alive(sources, tmp_path, monkeypatch, failure, control):
    directory, _, _ = sources
    if failure == "missing":
        # e.g. during a Pi app reinstall or data restore: the source databases are absent.
        directory = tmp_path / "reinstalling"
        directory.mkdir()
    else:
        # "schema": an unexpected error, e.g. door_events lost a column after a Pi app update.
        error = agent.SourceChangedError if failure == "changed" else IndexError

        def collect(self, directory):
            raise error("fixture")

        monkeypatch.setattr(agent.Store, "collect", collect)
    polls = []
    if control:
        # A relay-source problem must not take remote AC control (heartbeat + commands) offline.
        with pytest.raises(Stop):
            run_agent(monkeypatch, tmp_path, directory, control, lambda *a: polls.append(a))
        assert len(polls) == 8
    else:
        with pytest.raises(SystemExit):
            run_agent(monkeypatch, tmp_path, directory, control, lambda *a: polls.append(a))
        assert polls == []


def test_persistent_failures_do_not_flood_the_bounded_log(tmp_path, monkeypatch, caplog):
    directory = tmp_path / "reinstalling"
    directory.mkdir()

    def broken(*args):
        raise sqlite3.OperationalError("disk I/O error")

    def offline(*args):
        raise OSError("Pi app restarting")

    monkeypatch.setattr(agent, "dispatch", broken)
    caplog.set_level(logging.INFO)
    with pytest.raises(Stop):
        run_agent(monkeypatch, tmp_path, directory, True, offline)
    assert sorted(r.getMessage() for r in caplog.records) == [
        "CONTROL_TEMPORARILY_UNAVAILABLE kind=OSError",
        "RELAY_QUEUE_TEMPORARILY_UNAVAILABLE kind=OperationalError",
        "SOURCE_TEMPORARILY_UNAVAILABLE",
    ]


def toggle(directory, count, device="private-mac", at=1000.0, step=0.1):
    """Alternating open/closed transitions of one sensor, `step` s apart (flap or spoofed MQTT)."""
    with sqlite3.connect(directory / agent.SOURCES["door"][0]) as conn:
        for index in range(count):
            state, previous = ("open", "closed") if index % 2 == 0 else ("closed", "open")
            conn.execute(
                "INSERT INTO door_events VALUES(NULL,?,?,?,?)",
                (device, previous, state,
                 datetime.fromtimestamp(at + index * step, UTC).isoformat()),
            )


def drain(store):
    items = []
    while (item := store.next()) is not None:
        items.append(item)
        store.finish(item, "accepted")
    return items


def test_flapping_sensor_is_budgeted_and_coalesced_to_latest_state(sources, monkeypatch, caplog):
    directory, store, clock = sources
    store.collect(directory)
    monkeypatch.setattr(agent, "LOGGED", {})
    caplog.set_level(logging.WARNING)
    toggle(directory, 50)
    counts = store.collect(directory)
    # 10 relayed at once, one deferred event holds the latest transition, 39 intermediates dropped.
    assert counts["queued"] == agent.RELAY_BUDGET_TRANSITIONS + 1 and counts["coalesced"] == 39
    toggle(directory, 3, device="other-mac")
    assert store.collect(directory)["queued"] == 3  # another sensor keeps its own budget
    assert len(drain(store)) == agent.RELAY_BUDGET_TRANSITIONS + 3
    assert store.next() is None
    clock[0] += agent.RELAY_COALESCE_DELAY
    held = store.next()
    assert json.loads(held["payload"])["state"] == "closed"  # row 50 (index 49) closed the door
    toggle(directory, 5)
    assert store.collect(directory) | {"coalesced": 0, "queued": 0} == store.collect(directory)
    latest = store.next()
    assert latest["event_id"] != held["event_id"]
    assert json.loads(latest["payload"])["state"] == "open"  # superseded in place by row 58
    store.finish(latest, "accepted")
    assert store.next() is None
    with store.connect() as conn:
        assert conn.execute("SELECT last_id FROM cursors WHERE source='door'").fetchone()[0] == 58
        assert conn.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0] == 0
    clock[0] = 1100
    toggle(directory, 1, at=clock[0])  # still over budget: a new deferred slot (due 1160)
    assert store.collect(directory)["queued"] == 1 and store.next() is None
    clock[0] = 1000 + agent.RELAY_BUDGET_WINDOW
    toggle(directory, 2, at=clock[0])
    assert store.collect(directory)["queued"] == 2  # a new window refills the budget
    occurred = lambda item: json.loads(item["payload"])["occurred_at"]  # noqa: E731
    # The stale held transition (row 59) is superseded, never delivered after fresher states.
    assert sorted(occurred(item) for item in drain(store)) == [
        datetime.fromtimestamp(at, UTC).isoformat() for at in (1300.0, 1300.1)
    ]
    messages = [r.getMessage() for r in caplog.records if r.getMessage().startswith("RELAY_")]
    assert len(messages) == 1 and messages[0].endswith(" dropped=39")
    assert "private-mac" not in messages[0] and re.fullmatch(
        r"RELAY_COALESCED sensor=[0-9a-f]{12} dropped=39", messages[0])


def test_rate_limited_server_holds_every_pending_event_until_retry_after(sources, caplog):
    directory, store, clock = sources
    store.collect(directory)
    add(directory)
    add(directory, "automation")
    assert store.collect(directory)["queued"] == 2
    with store.connect() as conn:
        expected = {row[0] for row in conn.execute("SELECT event_id FROM outbox")}
    sender = agent.Sender({"endpoint": "https://example.test", "hub_token": "fixture-hub"})
    received = []

    class Accepted:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            return b'{"id":1,"duplicate":false}'

    class ThenAccept:
        calls = 0

        def open(self, request, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise urllib.error.HTTPError(
                    "https://example.test", 429, "rate_limited", {"Retry-After": "7"}, None
                )
            received.append(json.loads(request.data)["event_id"])
            return Accepted()

    sender.opener = ThenAccept()
    caplog.set_level(logging.INFO)
    assert agent.dispatch(store, sender)
    assert store.next() is None
    with store.connect() as conn:
        rows = conn.execute("SELECT state,attempts,due_at FROM outbox").fetchall()
    assert [tuple(row) for row in rows] == [("pending", 0, 1007.0)] * 2
    clock[0] = 1006
    assert not agent.dispatch(store, sender) and sender.opener.calls == 1
    clock[0] = 1007
    assert agent.dispatch(store, sender) and agent.dispatch(store, sender)
    assert not agent.dispatch(store, sender)
    assert sorted(received) == sorted(expected)  # each event exactly once, none dropped
    assert "CENTRAL_RELAY outcome=rate_limited wait=7" in [r.getMessage() for r in caplog.records]


@pytest.mark.parametrize(
    "headers,expected",
    [
        (None, 30.0),
        ({}, 30.0),
        ({"Retry-After": "7"}, 7.0),
        ({"Retry-After": "0"}, 1.0),
        ({"Retry-After": "999999"}, 300.0),
        ({"Retry-After": "soon"}, 30.0),
        ({"Retry-After": "Thu, 01 Jan 2015 00:00:00 GMT"}, 1.0),
    ],
)
def test_retry_after_is_parsed_and_bounded(headers, expected):
    assert agent.retry_after(headers) == expected
    date = agent.email.utils.formatdate(time.time() + 120, usegmt=True)
    assert 117 <= agent.retry_after({"Retry-After": date}) <= 121


def test_rate_limiting_never_stops_the_agent_or_hammers_server(sources, tmp_path, monkeypatch):
    directory, _, _ = sources
    store = agent.Store(tmp_path / "s/outbox.sqlite3")
    store.connection_test()

    class AlwaysLimited:
        calls = 0

        def open(self, request, **kwargs):
            self.calls += 1
            raise urllib.error.HTTPError(
                "https://example.test", 429, "rate_limited", {"Retry-After": "60"}, None
            )

    opener = AlwaysLimited()
    monkeypatch.setattr(agent.urllib.request, "build_opener", lambda *handlers: opener)
    with pytest.raises(Stop):  # eight loops with control off: no SystemExit, no failure count
        run_agent(monkeypatch, tmp_path, directory, False, lambda *a: None)
    assert opener.calls == 1
    with store.connect() as conn:
        rows = conn.execute("SELECT state,attempts FROM outbox").fetchall()
    assert [tuple(row) for row in rows] == [("pending", 0)]


def climate(directory, at, temperature, device="private-sensor-mac"):
    with sqlite3.connect(directory / "sensors/sensors.sqlite3") as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sensor_states(device_id TEXT PRIMARY KEY,kind TEXT,"
            "state_json TEXT,last_reported_at TEXT)"
        )
        conn.execute(
            "INSERT OR REPLACE INTO sensor_states VALUES(?,?,?,?)",
            (device, "temperature_humidity",
             json.dumps({"temperature_c": temperature, "humidity_percent": 50}),
             datetime.fromtimestamp(at, UTC).isoformat()),
        )


def test_climate_reports_relay_once_per_interval_while_the_cursor_keeps_moving(sources):
    directory, store, clock = sources
    climate(directory, 1000, 20)
    assert store.collect(directory)["climate_baseline"] == 1
    clock[0] = 1001
    climate(directory, 1001, 21)
    assert store.collect(directory)["climate_queued"] == 1
    for at in (1031, 1060.9):  # Z2M chatter inside the interval: skipped, never re-read
        clock[0] = at
        climate(directory, at, 22)
        counts = store.collect(directory)
        assert (counts["climate_skipped"], counts["climate_queued"]) == (1, 0)
        assert store.collect(directory)["climate_skipped"] == 0
        with store.connect() as conn:
            row = conn.execute("SELECT reported_at,relayed_at FROM climate_cursors").fetchone()
        assert tuple(row) == (at, 1001.0)
    clock[0] = 1061
    climate(directory, 1061, 23)
    climate(directory, 1061, 30, device="other-sensor-mac")  # its own first report
    assert store.collect(directory)["climate_queued"] == 2
    assert sorted(json.loads(i["payload"])["temperature_c"] for i in drain(store)) == [21, 23, 30]


def test_existing_outbox_gains_the_climate_relay_column_once(tmp_path):
    path = tmp_path / "legacy/outbox.sqlite3"
    path.parent.mkdir()
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE climate_cursors(sensor_ref TEXT PRIMARY KEY,"
                     "reported_at REAL NOT NULL)")
        conn.execute("INSERT INTO climate_cursors VALUES('s',1000.0)")
    for _ in range(2):  # the migration is additive and idempotent
        with agent.Store(path).connect() as conn:
            rows = conn.execute("SELECT sensor_ref,reported_at,relayed_at FROM climate_cursors")
            assert [tuple(row) for row in rows] == [("s", 1000.0, None)]


def test_transitions_and_warnings_leave_before_climate_also_after_a_hold(sources):
    directory, store, clock = sources
    store.collect(directory)
    with store.connect() as conn:
        store._enqueue(conn, "climate-1", "sensor.climate_report", {}, 1240)
        store._enqueue(conn, "climate-2", "sensor.climate_report", {}, 1240)
    add(directory)
    add(directory, "automation")
    assert store.collect(directory)["queued"] == 2
    assert [item["kind"] for item in drain(store)] == [
        "sensor.door_changed", "automation.warning_triggered",
        "sensor.climate_report", "sensor.climate_report",
    ]
    with store.connect() as conn:
        store._enqueue(conn, "climate-3", "sensor.climate_report", {}, 1240)
    add(directory)
    add(directory, "automation")
    store.collect(directory)
    store.finish({"event_id": "climate-3", "attempts": 0}, "rate_limited", wait=30)
    assert store.next() is None
    clock[0] = 1030
    assert [item["kind"] for item in drain(store)] == [
        "sensor.door_changed", "automation.warning_triggered", "sensor.climate_report",
    ]


def test_held_transition_from_a_restart_backlog_is_due_before_it_expires(sources):
    directory, store, clock = sources
    store.collect(directory)
    toggle(directory, 12, at=clock[0] - 200, step=1)  # agent was down: rows are 200..189 s old
    counts = store.collect(directory)
    assert (counts["queued"], counts["coalesced"]) == (11, 1)
    with store.connect() as conn:
        slot = conn.execute("SELECT * FROM outbox ORDER BY due_at DESC LIMIT 1").fetchone()
    # row 11 expires at +50 s: the slot is due at +45 s (not +60 s) and row 12 superseded it.
    assert (slot["due_at"], slot["expires_at"]) == (1045.0, 1051.0)
    assert json.loads(slot["payload"])["state"] == "closed"
    assert len(drain(store)) == 10 and store.next() is None
    clock[0] = 1045
    final = store.next()
    assert final["event_id"] == slot["event_id"] and final["state"] == "pending"


def test_held_transition_with_almost_no_window_left_is_sent_at_once(sources):
    directory, store, clock = sources
    store.collect(directory)
    toggle(directory, 11, at=clock[0] - 239.9)  # every row expires within about one second
    assert store.collect(directory)["queued"] == 11
    sent = drain(store)
    assert len(sent) == 11 and json.loads(sent[-1]["payload"])["state"] == "open"  # row 11
    with store.connect() as conn:
        left = conn.execute("SELECT COUNT(*) FROM outbox WHERE state!='accepted'").fetchone()[0]
    assert left == 0
