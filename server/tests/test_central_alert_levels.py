"""Alert categories x levels: routing, legacy switch mapping, schema 6 -> 7 backfill and FCM fields."""

import sqlite3
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
import central_server.storage as storage
from central_server.control import STATEMENTS as CONTROL_STATEMENTS
from central_server.households import Households, token_digest
from central_server.identity import STATEMENTS as IDENTITY_STATEMENTS
from central_server.identity import ensure_key
from central_server.preferences import STATEMENTS as PREFERENCE_STATEMENTS
from central_server.preferences import alert_category, category, levels
from central_server.push import PushStore
from central_server.push_schema import PUSH_STATEMENTS
from central_server.schema import STATEMENTS
from central_server.storage import SCHEMA_VERSION, initialize, ready

from tests.test_central_fcm import sender
from tests.test_central_households import environment as environment
from tests.test_central_push import setup as setup

DEFAULTS = dict(safety="urgent", security="alert", device="alert", environment="quiet",
                report="off", automation="alert", family="quiet")
SAMPLES = {"safety": "safety.fire", "security": "sensor.motion_detected", "device": "device.offline",
           "environment": "environment.too_hot", "report": "sensor.climate_report",
           "automation": "automation.rule_ran", "family": "family.member_joined",
           "other": "hub.connection_test"}
SECRET = "a" * 64


def options(**changes):
    return dict(door=True, climate=False, warning=True, climate_interval_minutes=5) | changes


def rows(db, sql, *params):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def recipients(db, event):
    return {row[0] for row in rows(db, "SELECT j.installation_id FROM push_jobs j JOIN push_messages m "
                                       "ON m.id=j.message_id WHERE m.event_id=?", event)}


def effective(db, installation, user):
    with sqlite3.connect(db) as conn:
        return levels(conn, installation, user)


def switches(db, installation):
    return rows(db, "SELECT door,climate,warning,climate_interval_minutes FROM notification_preferences "
                    "WHERE installation_id=?", installation)[0]


@pytest.mark.parametrize("kind,selected,legacy", [
    ("safety.fire", "safety", "other"), ("sensor.leak_detected", "safety", "other"),
    ("sensor.smoke_detected", "safety", "other"), ("sensor.door_changed", "security", "door"),
    ("sensor.open", "security", "door"), ("sensor.closed", "security", "door"),
    ("sensor.motion_detected", "security", "other"), ("device.offline", "device", "other"),
    ("environment.too_hot", "environment", "other"), ("sensor.climate_threshold", "environment", "other"),
    ("sensor.climate_report", "report", "climate"), ("automation.warning_triggered", "automation", "warning"),
    ("automation.rule_ran", "automation", "other"), ("family.member_joined", "family", "other"),
    ("hub.connection_test", "other", "other"), ("sensor.unknown", "other", "other"),
    ("safetyfirst", "other", "other"), ("devices.x", "other", "other"), (None, "other", "other"),
])
def test_kinds_map_to_categories_and_the_legacy_value_is_unchanged(kind, selected, legacy):
    assert alert_category(kind) == selected and category(kind) == legacy


def test_defaults_push_only_urgent_and_alert_categories(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    family = {ids[owner], ids[member]}
    for name, kind in SAMPLES.items():
        event = homes.ingest(hub["hub_token"], "default-" + name, kind, {})["id"]
        pushed = name == "other" or DEFAULTS[name] in ("urgent", "alert")
        assert recipients(db, event) == (family if pushed else set()), name


def test_saved_levels_route_each_phone_and_keep_legacy_switches_in_step(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    chosen = dict(safety="alert", security="quiet", device="off", environment="urgent",
                  report="urgent", automation="off", family="alert")
    assert push.set_levels(owner, ids[owner], SECRET, chosen, 15) == {
        "status": "saved", "levels": chosen, "report_interval_minutes": 15}
    assert switches(db, ids[owner]) == (0, 1, 0, 15)
    for name, kind in SAMPLES.items():
        event = homes.ingest(hub["hub_token"], "saved-" + name, kind, {})["id"]
        mine = name == "other" or chosen[name] in ("urgent", "alert")
        theirs = name == "other" or DEFAULTS[name] in ("urgent", "alert")  # the other phone is untouched
        expected = ({ids[owner]} if mine else set()) | ({ids[member]} if theirs else set())
        assert recipients(db, event) == expected, name


def test_levels_api_requires_installation_proof_and_exact_choices(environment):
    _, _, _, _, call = environment
    path = "/v1/installations/" + str(uuid.uuid4())
    call("owner", "PUT", path, dict(secret=SECRET, token="token_" + "x" * 40))
    body = dict(secret=SECRET, levels=dict(DEFAULTS), report_interval_minutes=5)
    saved = call("owner", "PUT", path + "/notification-levels", body)
    assert saved.status_code == 200
    assert saved.json == {"status": "saved", "levels": DEFAULTS, "report_interval_minutes": 5}
    assert call("outsider", "PUT", path + "/notification-levels", body).status_code == 404
    assert call("owner", "PUT", path + "/notification-levels", body | dict(secret="b" * 64)).status_code == 404
    missing = {name: value for name, value in DEFAULTS.items() if name != "family"}
    for chosen in (missing, DEFAULTS | dict(energy="alert"), DEFAULTS | dict(safety="off"),
                   DEFAULTS | dict(safety="quiet"), DEFAULTS | dict(security="loud"),
                   DEFAULTS | dict(security=None), DEFAULTS | dict(security=["alert"]),
                   DEFAULTS | dict(report="OFF"), [], "alert", None):
        refused = call("owner", "PUT", path + "/notification-levels", body | dict(levels=chosen))
        assert refused.status_code == 400 and refused.json == {"error": "invalid_notification_preferences"}
    for interval in (True, 2, "5", 5.0, None, 0):
        refused = call("owner", "PUT", path + "/notification-levels", body | dict(report_interval_minutes=interval))
        assert refused.status_code == 400 and refused.json == {"error": "invalid_notification_preferences"}
    without = {key: value for key, value in body.items() if key != "report_interval_minutes"}
    for shape in (body | dict(extra=True), without):
        refused = call("owner", "PUT", path + "/notification-levels", shape)
        assert refused.status_code == 400 and refused.json == {"error": "invalid_body"}
    bad = call("owner", "PUT", "/v1/installations/not-a-uuid/notification-levels", body)
    assert bad.status_code == 400 and bad.json == {"error": "invalid_body"}
    for value in ("quiet", "off"):  # the four non-safety values are all accepted elsewhere
        assert call("owner", "PUT", path + "/notification-levels",
                    body | dict(levels=DEFAULTS | dict(security=value))).status_code == 200


def test_legacy_switches_and_levels_follow_each_other(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    mine = ids[owner]
    push.set_preferences(owner, mine, SECRET, options(door=False, climate=True, warning=False,
                                                      climate_interval_minutes=1))
    assert effective(db, mine, owner) == DEFAULTS | dict(security="off", report="alert", automation="off")
    assert set(rows(db, "SELECT category,level FROM notification_levels WHERE installation_id=?", mine)) == {
        ("security", "off"), ("report", "alert"), ("automation", "off")}
    push.set_levels(owner, mine, SECRET, DEFAULTS | dict(security="urgent", report="quiet",
                                                         automation="quiet"), 60)
    assert switches(db, mine) == (1, 0, 0, 60)
    # An old build always re-sends all three switches: a switch that keeps its meaning keeps the
    # finer level, a switch that flips becomes alert or off.
    response = push.set_preferences(owner, mine, SECRET, options(warning=True))
    assert response == {"status": "saved", "preferences": options(warning=True)}
    assert effective(db, mine, owner) == DEFAULTS | dict(security="urgent", report="quiet",
                                                         automation="alert")
    push.set_preferences(owner, mine, SECRET, options(door=False, climate=True))
    assert effective(db, mine, owner) == DEFAULTS | dict(security="off", report="alert",
                                                         automation="alert")
    door = homes.ingest(hub["hub_token"], "legacy-door", "sensor.door_changed", {})["id"]
    assert recipients(db, door) == {ids[member]}


def test_a_previous_accounts_choices_never_apply_to_the_next_account(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    phone = ids[member]
    push.set_levels(member, phone, SECRET, DEFAULTS | dict(security="off", family="urgent"), 5)
    push.register(outsider, phone, SECRET, "token_" + "1" * 40)  # the phone signs in as another account
    assert effective(db, phone, outsider) == DEFAULTS
    push.set_preferences(outsider, phone, SECRET, options(climate=True))
    assert set(rows(db, "SELECT user_id FROM notification_levels WHERE installation_id=?", phone)) == {
        (outsider,)}
    assert effective(db, phone, outsider) == DEFAULTS | dict(report="alert")


def test_report_interval_is_still_enforced_per_phone(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(report="urgent"), 1)

    def report(name):
        return recipients(db, homes.ingest(hub["hub_token"], name, "sensor.climate_report", {})["id"])
    assert report("climate-1") == {ids[owner]}
    now[0] += 59
    assert report("climate-2") == set()
    now[0] += 1
    assert report("climate-3") == {ids[owner]}
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(report="alert"), 1)  # same account
    now[0] += 30
    assert report("climate-4") == set()  # saving again does not reset the interval clock
    now[0] += 30
    assert report("climate-5") == {ids[owner]}
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(report="quiet"), 1)
    now[0] += 3600
    assert report("climate-6") == set()


def test_queued_job_rechecks_level_and_fcm_carries_only_category_and_level(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup

    def jobs():
        claimed = {}
        while job := push.claim():
            claimed[job[1]] = job
        return claimed
    homes.ingest(hub["hub_token"], "door-1", "sensor.door_changed",
                 {"device_id": "a" * 32, "name": "현관문", "room": "현관"})
    queued = jobs()
    push.set_levels(member, ids[member], SECRET, DEFAULTS | dict(security="quiet"), 5)
    assert push.authorized(queued[ids[member]]) is None  # changed after queueing: not sent
    assert rows(db, "SELECT state FROM push_jobs WHERE installation_id=?", ids[member]) == [("cancelled",)]
    door = push.authorized(queued[ids[owner]])
    assert (door["category"], door["alert_category"], door["level"]) == ("door", "security", "alert")
    assert "현관" not in str(door) and "a" * 32 not in str(door) and "payload" not in door
    push.finish(queued[ids[owner]], "accepted")

    homes.ingest(hub["hub_token"], "leak-1", "sensor.leak_detected", {"room": "욕실"})
    leak = push.authorized(jobs()[ids[owner]])
    assert (leak["category"], leak["alert_category"], leak["level"]) == ("other", "safety", "urgent")
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(report="alert"), 1)
    homes.ingest(hub["hub_token"], "climate-1", "sensor.climate_report", {"temperature_c": 24})
    report = push.authorized(jobs()[ids[owner]])
    assert (report["category"], report["alert_category"], report["level"]) == ("climate", "report", "alert")
    push.test(home, owner, ids[owner])
    test = push.authorized(jobs()[ids[owner]])
    assert (test["category"], test["alert_category"], test["level"]) == ("other", "other", "alert")

    for recipient, priority in ((door, "HIGH"), (leak, "HIGH"), (report, "NORMAL"), (test, "HIGH")):
        item, calls = sender(200)
        assert item.send(recipient | {"expires_at": time.time() + 250}) == ("accepted", 0)
        message = calls[0][1]["json"]["message"]
        assert message["android"]["priority"] == priority
        assert {key: message["data"][key] for key in ("category", "alert_category", "level")} == {
            key: recipient[key] for key in ("category", "alert_category", "level")}
        assert not any(text in str(message) for text in ("현관", "욕실", "temperature", "a" * 32))


def test_discarded_installation_takes_its_levels(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    push.set_levels(owner, ids[owner], SECRET, DEFAULTS | dict(family="urgent"), 5)
    binding = rows(db, "SELECT binding FROM installations WHERE id=?", ids[owner])[0][0]
    push.unregister(owner, ids[owner], SECRET, binding)
    now[0] += 31 * 86400
    push.prune()
    assert rows(db, "SELECT COUNT(*) FROM installations WHERE id=?", ids[owner]) == [(0,)]
    assert rows(db, "SELECT COUNT(*) FROM notification_levels WHERE installation_id=?", ids[owner]) == [(0,)]
    assert rows(db, "PRAGMA foreign_key_check") == []


def schema_six(db):
    """A real schema-6 database, built from the statements each earlier version shipped."""
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE runtime_metadata (id INTEGER PRIMARY KEY CHECK(id=1), "
                     "installation_id TEXT NOT NULL, created_at TEXT NOT NULL)")
        conn.execute("INSERT INTO runtime_metadata VALUES (1,'keep-runtime','keep-created')")
        for statement in (*STATEMENTS, *PUSH_STATEMENTS, *PREFERENCE_STATEMENTS, *CONTROL_STATEMENTS,
                          *IDENTITY_STATEMENTS):
            conn.execute(statement)
        ensure_key(conn, now=1.0)
        for user in ("u1", "u2", "u3", "u4"):
            conn.execute("INSERT INTO users VALUES (?,'issuer',?,?,1)", (user, user, user + "@example.test"))
        conn.execute("INSERT INTO homes VALUES ('h','keep-home','u1',1)")
        for user, role in (("u1", "owner"), ("u2", "member"), ("u3", "viewer")):
            conn.execute("INSERT INTO memberships VALUES ('h',?,?,1,NULL)", (user, role))
        conn.execute("INSERT INTO hubs VALUES ('hub-1',?,NULL,0,'h',1)", (token_digest("hub", "hub_fixture"),))
        for index, user in enumerate(("u1", "u2", "u3", "u4"), 1):
            conn.execute("INSERT INTO installations VALUES (?,?,?,?,?,1,1000)",
                         ("p" + str(index), token_digest("installation", SECRET), user,
                          "token-" + str(index), "binding-" + str(index)))
        conn.executemany("INSERT INTO notification_preferences VALUES (?,?,?,?,?,?,?)",
                         [("p1", "u1", 1, 0, 1, 5, 0), ("p2", "u2", 0, 1, 0, 1, 900.0),
                          ("p3", "u3", 1, 1, 0, 15, 0)])
        conn.execute("INSERT INTO events(home_id,hub_id,sender_event_id,kind,payload,content_digest,"
                     "received_at) VALUES ('h','hub-1','old','sensor.open','{}','digest',500)")
        conn.execute("INSERT INTO control_hubs VALUES ('hub-1',900)")
        conn.execute("INSERT INTO control_devices VALUES ('hub-1',?,'거실 에어컨',1)", ("c" * 32,))
        conn.execute("PRAGMA user_version=6")


def test_schema_six_upgrade_backfills_levels_and_preserves_every_row(tmp_path):
    db = tmp_path / "central.sqlite3"
    schema_six(db)
    tables = [row[0] for row in rows(db, "SELECT name FROM sqlite_master WHERE type='table' "
                                         "AND name NOT LIKE 'sqlite_%'")]
    before = {table: rows(db, "SELECT * FROM " + table) for table in tables}
    initialize(db)
    initialize(db)
    assert SCHEMA_VERSION == 8 and rows(db, "PRAGMA user_version") == [(8,)] and ready(db)
    assert {table: rows(db, "SELECT * FROM " + table) for table in tables} == before
    assert set(rows(db, "SELECT installation_id,user_id,category,level FROM notification_levels")) == {
        ("p1", "u1", "security", "alert"), ("p1", "u1", "report", "off"), ("p1", "u1", "automation", "alert"),
        ("p2", "u2", "security", "off"), ("p2", "u2", "report", "alert"), ("p2", "u2", "automation", "off"),
        ("p3", "u3", "security", "alert"), ("p3", "u3", "report", "alert"), ("p3", "u3", "automation", "off")}
    assert rows(db, "SELECT COUNT(*) FROM hub_devices") == rows(db, "SELECT COUNT(*) FROM hub_inventory") == [(0,)]
    assert rows(db, "PRAGMA integrity_check") == [("ok",)] and rows(db, "PRAGMA foreign_key_check") == []
    # The carried-over choices route the next events exactly as the old switches did.
    homes = Households(db, clock=lambda: 2000.0)
    for name, kind, expected in (("door", "sensor.door_changed", {"p1", "p3"}),
                                 ("climate", "sensor.climate_report", {"p2", "p3"}),
                                 ("warning", "automation.warning_triggered", {"p1"}),
                                 ("leak", "sensor.leak_detected", {"p1", "p2", "p3"}),
                                 ("hot", "environment.too_hot", set())):
        assert recipients(db, homes.ingest("hub_fixture", name, kind, {})["id"]) == expected, name
    # The existing phones keep working through the new API after the upgrade.
    saved = PushStore(db, clock=lambda: 2000.0).set_levels("u2", "p2", SECRET, DEFAULTS, 60)
    assert saved["levels"] == DEFAULTS and switches(db, "p2") == (1, 0, 1, 60)


def test_failed_upgrade_rolls_back_to_schema_six(tmp_path, monkeypatch):
    db = tmp_path / "central.sqlite3"
    schema_six(db)
    monkeypatch.setattr(storage, "LEVEL_STATEMENTS", (*storage.LEVEL_STATEMENTS, "INVALID SQL"))
    with pytest.raises(sqlite3.Error):
        initialize(db)
    assert rows(db, "PRAGMA user_version") == [(6,)]
    assert rows(db, "SELECT name FROM sqlite_master WHERE name IN "
                    "('hub_devices','hub_inventory','notification_levels')") == []
    monkeypatch.undo()
    initialize(db)
    assert rows(db, "SELECT COUNT(*) FROM notification_levels") == [(9,)]


def test_schema_six_with_an_unexpected_table_is_preserved(tmp_path):
    db = tmp_path / "central.sqlite3"
    schema_six(db)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE hub_devices(owner_data TEXT)")
    with pytest.raises(RuntimeError, match="preserve"):
        initialize(db)
    assert rows(db, "PRAGMA user_version") == [(6,)]
