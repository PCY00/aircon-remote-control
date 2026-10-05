"""Independent phone consent, durable interval limits and deletion authority boundaries."""

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
from central_server.households import APIError
from central_server.push import PushStore
from central_server.push_schema import PUSH_STATEMENTS
from central_server.schema import STATEMENTS
from central_server.storage import initialize

from tests.test_central_households import environment as environment
from tests.test_central_push import setup as setup


def options(**changes):
    return dict(door=True, climate=False, warning=True, climate_interval_minutes=5) | changes


def recipients(db, event):
    with sqlite3.connect(db) as conn:
        return {
            r[0]
            for r in conn.execute(
                "SELECT j.installation_id FROM push_jobs j JOIN push_messages m "
                "ON m.id=j.message_id "
                "WHERE m.event_id=?",
                (event,),
            )
        }


def test_same_account_phone_selection_and_late_opt_out_cancel_queued_event(setup):
    db, _, homes, push, owner, member, _, home, _, ids, hub = setup
    second = str(uuid.uuid4())
    push.register(owner, second, "b" * 64, "second_" + "x" * 40)
    push.set_preferences(owner, second, "b" * 64, options(door=False))
    event = homes.ingest(hub["hub_token"], "door-one", "sensor.door_changed", {"state": "open"})
    assert recipients(db, event["id"]) == {ids[owner], ids[member]}
    push.set_preferences(owner, ids[owner], "a" * 64, options(door=False))
    while job := push.claim():
        allowed = push.authorized(job)
        if job[1] == ids[owner]:
            assert allowed is None
        elif allowed:
            push.finish(job, "accepted")
    assert push.test(home, owner, second)["queued"] == 1


def test_climate_is_opt_in_and_interval_survives_worker_restart(setup):
    db, now, homes, push, owner, _, _, _, _, ids, hub = setup
    first = homes.ingest(
        hub["hub_token"], "climate-1", "sensor.climate_report", {"temperature_c": 24}
    )
    assert recipients(db, first["id"]) == set()
    push.set_preferences(
        owner, ids[owner], "a" * 64, options(climate=True, climate_interval_minutes=1)
    )
    first = homes.ingest(
        hub["hub_token"], "climate-2", "sensor.climate_report", {"temperature_c": 25}
    )
    assert recipients(db, first["id"]) == {ids[owner]}
    now[0] += 59
    assert (
        recipients(
            db, homes.ingest(hub["hub_token"], "climate-3", "sensor.climate_report", {})["id"]
        )
        == set()
    )
    push = PushStore(db, clock=lambda: now[0])
    push.set_preferences(
        owner, ids[owner], "a" * 64, options(climate=True, climate_interval_minutes=1)
    )
    now[0] += 1
    assert recipients(
        db, homes.ingest(hub["hub_token"], "climate-4", "sensor.climate_report", {})["id"]
    ) == {ids[owner]}


def test_preference_api_requires_current_user_installation_proof_and_strict_types(environment):
    _, _, _, _, call = environment
    device = str(uuid.uuid4())
    path = "/v1/installations/" + device
    call("owner", "PUT", path, dict(secret="a" * 64, token="token_" + "x" * 40))
    body = dict(secret="a" * 64) | options()
    assert call("owner", "PUT", path + "/preferences", body).status_code == 200
    assert call("outsider", "PUT", path + "/preferences", body).status_code == 404
    assert (
        call("owner", "PUT", path + "/preferences", body | dict(secret="b" * 64)).status_code == 404
    )
    for change in (
        dict(door=1),
        dict(climate_interval_minutes=True),
        dict(climate_interval_minutes=0),
        dict(extra=True),
    ):
        assert call("owner", "PUT", path + "/preferences", body | change).status_code == 400


def test_delete_requires_owner_and_name_then_revokes_home_hub_invite_and_pending_push(setup):
    db, _, homes, push, owner, member, outsider, home, _, ids, hub = setup
    invite = homes.invitation(home, owner, "outsider@example.test", "member")
    homes.ingest(hub["hub_token"], "before-delete", "sensor.door_changed", {"state": "open"})
    for actor in (member, outsider):
        with pytest.raises(APIError):
            homes.delete_home(home, actor, "one")
    with pytest.raises(APIError) as wrong:
        homes.delete_home(home, owner, "wrong")
    assert wrong.value.code == "confirmation_required"
    assert homes.home(home, owner)["name"] == "one"
    assert homes.delete_home(home, owner, "one")["status"] == "deleted"
    assert homes.homes(owner) == [] and homes.homes(member) == []
    for action in (
        lambda: homes.home(home, owner),
        lambda: homes.events(home, member),
        lambda: homes.ingest(hub["hub_token"], "late", "sensor.door_changed", {}),
        lambda: homes.accept(outsider, invite["invitation_token"]),
    ):
        with pytest.raises(APIError):
            action()
    assert push.claim() is None
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM events WHERE home_id=?", (home,)).fetchone()[0] == 1
        )
        assert conn.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert homes.create_home(owner, "replacement")["role"] == "owner"


def test_schema_three_upgrade_preserves_registered_devices_and_existing_home(tmp_path):
    db = tmp_path / "existing.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE runtime_metadata(id INTEGER PRIMARY KEY,"
            "installation_id TEXT,created_at TEXT)"
        )
        conn.execute("INSERT INTO runtime_metadata VALUES(1,'keep','created')")
        for statement in (*STATEMENTS, *PUSH_STATEMENTS):
            conn.execute(statement)
        conn.execute("INSERT INTO users VALUES('u','i','s','e',1)")
        conn.execute("INSERT INTO homes VALUES('h','existing','u')")
        conn.execute("INSERT INTO memberships VALUES('h','u','owner',1,NULL)")
        conn.execute(
            "INSERT INTO installations VALUES('phone','proof','u','private-token','binding',1,1000)"
        )
        conn.execute("PRAGMA user_version=3")
    initialize(db)
    initialize(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name,active FROM homes").fetchall() == [("existing", 1)]
        assert conn.execute("SELECT token,binding FROM installations").fetchall() == [
            ("private-token", "binding")
        ]
        assert conn.execute("SELECT COUNT(*) FROM notification_preferences").fetchone() == (0,)
        assert conn.execute("PRAGMA user_version").fetchone() == (4,)
