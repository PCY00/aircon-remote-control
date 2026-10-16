"""Server-side quiet hours for the iPhone web app: validation, window math, delivery, schema 7 -> 8."""

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
import central_server.storage as storage
from central_server.control import STATEMENTS as CONTROL_STATEMENTS
from central_server.households import Households, token_digest
from central_server.identity import STATEMENTS as IDENTITY_STATEMENTS
from central_server.identity import ensure_key
from central_server.inventory import STATEMENTS as INVENTORY_STATEMENTS
from central_server.preferences import LEVEL_STATEMENTS, in_quiet_window
from central_server.preferences import STATEMENTS as PREFERENCE_STATEMENTS
from central_server.push import PushStore
from central_server.push_schema import PUSH_STATEMENTS
from central_server.schema import STATEMENTS
from central_server.storage import SCHEMA_VERSION, initialize, ready

from tests.test_central_households import environment as environment
from tests.test_central_push import setup as setup

SECRET = "a" * 64
DEFAULTS = dict(safety="urgent", security="alert", device="alert", environment="quiet",
                report="off", automation="alert", family="quiet")


def hours(enabled=True, start=0, end=0, offset=0):
    return dict(enabled=enabled, start_minute=start, end_minute=end, utc_offset_minutes=offset)


def rows(db, sql, *params):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def recipients(db, event):
    return {row[0] for row in rows(db, "SELECT j.installation_id FROM push_jobs j JOIN push_messages m "
                                       "ON m.id=j.message_id WHERE m.event_id=?", event)}


def at(hour, minute, second=0, day=20000):
    """Epoch seconds of a UTC wall-clock time on an arbitrary day."""
    return day * 86400 + hour * 3600 + minute * 60 + second


@pytest.mark.parametrize("start,end,offset,now,inside", [
    # 22:00-07:00 in Korea (UTC+9): wraps past midnight, start inclusive, end exclusive.
    (1320, 420, 540, at(14, 0), True),     # 23:00 local
    (1320, 420, 540, at(13, 0), True),     # 22:00 local, the first minute
    (1320, 420, 540, at(12, 59, 59), False),  # 21:59:59 local
    (1320, 420, 540, at(21, 59, 59), True),   # 06:59:59 local
    (1320, 420, 540, at(22, 0), False),    # 07:00 local, the end minute is outside
    (1320, 420, 540, at(3, 0), False),     # 12:00 local
    (1320, 420, 540, at(15, 0), True),     # 00:00 local, past midnight
    # Same-day window without an offset.
    (60, 120, 0, at(1, 0), True),
    (60, 120, 0, at(1, 59, 59), True),
    (60, 120, 0, at(2, 0), False),
    (60, 120, 0, at(0, 59, 59), False),
    # Negative offset: UTC-5 local midnight to 01:00.
    (0, 60, -300, at(5, 30), True),        # 00:30 local
    (0, 60, -300, at(4, 30), False),       # 23:30 local the previous day
    # The widest offsets move the local day across the UTC date line.
    (840, 841, 840, at(0, 0), True),       # UTC+14: 14:00 local
    (600, 601, -840, at(0, 0), True),      # UTC-14: 10:00 local the previous day
    (0, 1439, 0, at(23, 59), False),       # the last minute of the day is outside [0, 1439)
    (1439, 0, 0, at(23, 59), True),        # one-minute window that wraps
    (1439, 0, 0, at(0, 0), False),
])
def test_window_math(start, end, offset, now, inside):
    assert in_quiet_window(start, end, offset, now) is inside


@pytest.mark.parametrize("minute", [0, 1, 539, 540, 720, 1439])
def test_equal_start_and_end_never_apply(minute):
    assert not in_quiet_window(540, 540, 0, at(0, 0) + minute * 60)
    assert not in_quiet_window(0, 0, 0, at(0, 0) + minute * 60)


def test_api_saves_with_installation_proof_and_strict_types(environment):
    db, _, _, _, call = environment
    installation = str(uuid.uuid4())
    path = "/v1/installations/" + installation
    call("owner", "PUT", path, dict(secret=SECRET, token="token_" + "x" * 40))
    body = dict(secret=SECRET) | hours(True, 1320, 420, 540)
    saved = call("owner", "PUT", path + "/quiet-hours", body)
    assert saved.status_code == 200
    assert saved.json == {"status": "saved", "quiet_hours": hours(True, 1320, 420, 540)}
    assert SECRET not in saved.text
    assert rows(db, "SELECT enabled,start_minute,end_minute,utc_offset_minutes FROM quiet_hours "
                    "WHERE installation_id=?", installation) == [(1, 1320, 420, 540)]
    assert call("outsider", "PUT", path + "/quiet-hours", body).status_code == 404
    assert call("owner", "PUT", path + "/quiet-hours", body | dict(secret="b" * 64)).status_code == 404
    for name, values in (("enabled", (1, 0, "true", None, [])),
                         ("start_minute", (True, -1, 1440, "10", 10.0, None)),
                         ("end_minute", (False, -1, 1440, "420", 420.5, [])),
                         ("utc_offset_minutes", (True, -841, 841, 1.5, "540", None))):
        for value in values:
            refused = call("owner", "PUT", path + "/quiet-hours", body | {name: value})
            assert refused.status_code == 400, (name, value)
            assert refused.json == {"error": "invalid_quiet_hours"}
    without = {key: value for key, value in body.items() if key != "utc_offset_minutes"}
    for shape in (body | dict(extra=True), without, dict(secret=SECRET)):
        refused = call("owner", "PUT", path + "/quiet-hours", shape)
        assert refused.status_code == 400 and refused.json == {"error": "invalid_body"}
    bad = call("owner", "PUT", "/v1/installations/not-a-uuid/quiet-hours", body)
    assert bad.status_code == 400 and bad.json == {"error": "invalid_body"}
    for edge in (hours(False, 0, 1439, -840), hours(True, 1439, 0, 840), hours(True, 5, 5, 0)):
        accepted = call("owner", "PUT", path + "/quiet-hours", dict(secret=SECRET) | edge)
        assert accepted.status_code == 200 and accepted.json["quiet_hours"] == edge
    assert rows(db, "SELECT COUNT(*) FROM quiet_hours") == [(1,)]  # replaced, never duplicated


def test_alert_is_held_back_but_urgent_and_other_are_delivered(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    # now = 1000 s: 00:16 UTC, 09:16 in Korea. 09:00-10:00 Korean time is quiet for the owner only.
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 540, 600, 540))
    family = {ids[owner], ids[member]}
    for name, kind, expected in (("door", "sensor.door_changed", {ids[member]}),
                                 ("device", "device.offline", {ids[member]}),
                                 ("leak", "sensor.leak_detected", family),
                                 ("fire", "safety.fire", family),
                                 ("test", "hub.connection_test", family),
                                 ("unknown", "sensor.unknown", family),
                                 ("hot", "environment.too_hot", set())):  # quiet level: never pushed
        assert recipients(db, homes.ingest(hub["hub_token"], name, kind, {})["id"]) == expected, name
    assert push.test(home, owner, ids[owner])["queued"] == 1  # the owner's connection test still goes
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(security="urgent"), 5)
    assert recipients(db, homes.ingest(hub["hub_token"], "door-2", "sensor.door_changed", {})["id"]) == family
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(False, 540, 600, 540))
    assert recipients(db, homes.ingest(hub["hub_token"], "device-2", "device.offline", {})["id"]) == family
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 540, 540, 540))  # empty window
    assert recipients(db, homes.ingest(hub["hub_token"], "device-3", "device.offline", {})["id"]) == family
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 540, 600, 540))
    now[0] += 3600  # 10:16 in Korea: the window has ended
    assert recipients(db, homes.ingest(hub["hub_token"], "device-4", "device.offline", {})["id"]) == family


def test_held_back_report_keeps_the_interval_clock(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(report="alert"), 60)
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 0, 30, 0))  # 00:00-00:30 UTC

    def report(name):
        return recipients(db, homes.ingest(hub["hub_token"], name, "sensor.climate_report", {})["id"])
    assert report("climate-1") == set()
    assert rows(db, "SELECT last_climate_at FROM notification_preferences WHERE installation_id=?",
                ids[owner]) == [(0,)]
    now[0] += 900  # 00:31 UTC
    assert report("climate-2") == {ids[owner]}  # first report after quiet hours is not delayed
    now[0] += 60
    assert report("climate-3") == set()  # the 60-minute interval still applies as before


def test_queued_alert_is_cancelled_when_quiet_hours_apply_at_send_time(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup

    def jobs():
        claimed = {}
        while job := push.claim():
            claimed.setdefault(job[1], []).append(job)
        return claimed
    homes.ingest(hub["hub_token"], "door-1", "sensor.door_changed", {})
    homes.ingest(hub["hub_token"], "leak-1", "sensor.leak_detected", {})
    push.test(home, owner, ids[owner])
    # Saved after queueing: 00:18-00:30 UTC, and the send happens at 00:18:40.
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 18, 30, 0))
    now[0] += 120
    queued = jobs()
    results = set()
    for job in queued[ids[owner]]:
        recipient = push.authorized(job)
        results.add(recipient["alert_category"] if recipient else None)
    assert results == {None, "safety", "other"}  # the door alert is dropped, leak and test go
    assert rows(db, "SELECT j.state,j.last_error FROM push_jobs j JOIN push_messages m ON m.id=j.message_id "
                    "JOIN events e ON e.id=m.event_id WHERE e.kind='sensor.door_changed' "
                    "AND j.installation_id=?", ids[owner]) == [("cancelled", "quiet_hours")]
    member_jobs = queued[ids[member]]
    assert {push.authorized(job)["alert_category"] for job in member_jobs} == {"security", "safety"}


def test_a_previous_accounts_quiet_hours_never_apply_to_the_next_account(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    phone = ids[member]
    push.set_quiet_hours(member, phone, SECRET, hours(True, 0, 1439, 0))
    push.register(owner, phone, SECRET, "token_" + "9" * 40)  # the phone signs in as the owner
    event = homes.ingest(hub["hub_token"], "door-1", "sensor.door_changed", {})["id"]
    assert phone in recipients(db, event)
    saved = push.set_quiet_hours(owner, phone, SECRET, hours(True, 0, 1439, 0))
    assert saved == {"status": "saved", "quiet_hours": hours(True, 0, 1439, 0)}
    assert rows(db, "SELECT user_id FROM quiet_hours WHERE installation_id=?", phone) == [(owner,)]
    event = homes.ingest(hub["hub_token"], "door-2", "sensor.door_changed", {})["id"]
    assert phone not in recipients(db, event)


def test_discarded_installation_takes_its_quiet_hours(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    push.set_quiet_hours(owner, ids[owner], SECRET, hours(True, 1320, 420, 540))
    binding = rows(db, "SELECT binding FROM installations WHERE id=?", ids[owner])[0][0]
    push.unregister(owner, ids[owner], SECRET, binding)
    now[0] += 31 * 86400
    push.prune()
    assert rows(db, "SELECT COUNT(*) FROM installations WHERE id=?", ids[owner]) == [(0,)]
    assert rows(db, "SELECT COUNT(*) FROM quiet_hours WHERE installation_id=?", ids[owner]) == [(0,)]
    assert rows(db, "PRAGMA foreign_key_check") == []


def schema_seven(db):
    """A real schema-7 database, built from the statements each earlier version shipped."""
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runtime_metadata (id INTEGER PRIMARY KEY CHECK(id=1), "
                     "installation_id TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO runtime_metadata VALUES (1,'keep-runtime','keep-created')")
        for statement in (*STATEMENTS, *PUSH_STATEMENTS, *PREFERENCE_STATEMENTS, *CONTROL_STATEMENTS,
                          *IDENTITY_STATEMENTS, *INVENTORY_STATEMENTS, *LEVEL_STATEMENTS):
            conn.execute(statement)
        ensure_key(conn, now=1.0)
        for user in ("u1", "u2"):
            conn.execute("INSERT INTO users VALUES (?,'issuer',?,?,1)", (user, user, user + "@example.test"))
        conn.execute("INSERT INTO homes VALUES ('h','keep-home','u1',1)")
        conn.execute("INSERT INTO memberships VALUES ('h','u1','owner',1,NULL)")
        conn.execute("INSERT INTO memberships VALUES ('h','u2','member',1,NULL)")
        conn.execute("INSERT INTO hubs VALUES ('hub-1',?,NULL,0,'h',1)", (token_digest("hub", "hub_fixture"),))
        for index, user in enumerate(("u1", "u2"), 1):
            conn.execute("INSERT INTO installations VALUES (?,?,?,?,?,1,1000)",
                         ("p" + str(index), token_digest("installation", SECRET), user,
                          "token-" + str(index), "binding-" + str(index)))
        conn.execute("INSERT INTO notification_preferences VALUES ('p1','u1',1,0,1,5,0)")
        conn.executemany("INSERT INTO notification_levels VALUES (?,?,?,?)",
                         [("p1", "u1", "security", "alert"), ("p2", "u2", "device", "urgent")])
        conn.execute("INSERT INTO events(home_id,hub_id,sender_event_id,kind,payload,content_digest,"
                     "received_at) VALUES ('h','hub-1','old','sensor.open','{}','digest',500)")
        conn.execute("INSERT INTO control_hubs VALUES ('hub-1',900)")
        conn.execute("INSERT INTO control_devices VALUES ('hub-1',?,'거실 에어컨',1)", ("c" * 32,))
        conn.execute("INSERT INTO hub_inventory VALUES ('hub-1',900)")
        conn.execute("INSERT INTO hub_devices VALUES ('hub-1',?,0,'현관문','현관','door_sensor',"
                     "'[\"contact\"]','{\"contact\":\"closed\"}',800,0)", ("d" * 32,))
        conn.execute("PRAGMA user_version=7")


def test_schema_seven_upgrade_adds_an_empty_table_and_preserves_every_row(tmp_path):
    db = tmp_path / "central.sqlite3"
    schema_seven(db)
    tables = [row[0] for row in rows(db, "SELECT name FROM sqlite_master WHERE type='table' "
                                         "AND name NOT LIKE 'sqlite_%'")]
    before = {table: rows(db, "SELECT * FROM " + table) for table in tables}
    initialize(db)
    initialize(db)
    assert SCHEMA_VERSION == 8 and rows(db, "PRAGMA user_version") == [(8,)] and ready(db)
    assert {table: rows(db, "SELECT * FROM " + table) for table in tables} == before
    assert rows(db, "SELECT COUNT(*) FROM quiet_hours") == [(0,)]
    assert rows(db, "PRAGMA integrity_check") == [("ok",)] and rows(db, "PRAGMA foreign_key_check") == []
    # Existing phones keep receiving as before, and the new route works on the upgraded data.
    homes = Households(db, clock=lambda: 2000.0)
    door = homes.ingest("hub_fixture", "door", "sensor.door_changed", {})["id"]
    assert recipients(db, door) == {"p1", "p2"}
    saved = PushStore(db, clock=lambda: 2000.0).set_quiet_hours("u1", "p1", SECRET, hours(True, 0, 1439, 0))
    assert saved["quiet_hours"] == hours(True, 0, 1439, 0)
    door = homes.ingest("hub_fixture", "door-2", "sensor.door_changed", {})["id"]
    assert recipients(db, door) == {"p2"}


def test_failed_upgrade_rolls_back_to_schema_seven(tmp_path, monkeypatch):
    db = tmp_path / "central.sqlite3"
    schema_seven(db)
    monkeypatch.setattr(storage, "QUIET_STATEMENTS", (*storage.QUIET_STATEMENTS, "INVALID SQL"))
    with pytest.raises(sqlite3.Error):
        initialize(db)
    assert rows(db, "PRAGMA user_version") == [(7,)]
    assert rows(db, "SELECT name FROM sqlite_master WHERE name='quiet_hours'") == []
    monkeypatch.undo()
    initialize(db)
    assert rows(db, "PRAGMA user_version") == [(8,)]


def test_schema_seven_with_an_unexpected_table_is_preserved(tmp_path):
    db = tmp_path / "central.sqlite3"
    schema_seven(db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE quiet_hours(owner_data TEXT)")
        conn.execute("INSERT INTO quiet_hours VALUES ('keep')")
    with pytest.raises(RuntimeError, match="preserve"):
        initialize(db)
    assert rows(db, "PRAGMA user_version") == [(7,)]
    assert rows(db, "SELECT owner_data FROM quiet_hours") == [("keep",)]
