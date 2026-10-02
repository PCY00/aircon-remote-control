"""Privacy, durable dispatch, revocation races and additive migration contracts."""

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services/central-server"))
from central_server.households import APIError, Households, Identity
from central_server.push import PushStore, PushWorker
from central_server.schema import STATEMENTS
from central_server.storage import initialize


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "central.sqlite3"
    initialize(db)
    now = [1000.0]
    homes = Households(db, clock=lambda: now[0])
    push = PushStore(db, clock=lambda: now[0])
    owner = homes.user(Identity("issuer", "owner", "owner@example.test"))
    member = homes.user(Identity("issuer", "member", "member@example.test"))
    outsider = homes.user(Identity("issuer", "outsider", "outsider@example.test"))
    home = homes.create_home(owner, "one")["id"]
    other = homes.create_home(outsider, "two")["id"]
    invite = homes.invitation(home, owner, "member@example.test", "viewer")
    homes.accept(member, invite["invitation_token"])
    ids = {user: str(uuid.uuid4()) for user in (owner, member, outsider)}
    for index, user in enumerate(ids):
        push.register(user, ids[user], "a" * 64, "token_" + str(index) * 40)
    hub = homes.provision_hub()
    homes.claim(home, owner, hub["claim_code"])
    return db, now, homes, push, owner, member, outsider, home, other, ids, hub


def event(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    return homes.ingest(hub["hub_token"], "same-event", "sensor.open", {"private": "never in push"})


def rows(db, sql):
    with sqlite3.connect(db) as c:
        return c.execute(sql).fetchall()


def test_event_and_recipients_commit_once_for_active_family_only(setup):
    db, _, _, _, owner, member, outsider, *_ = setup
    first = event(setup)
    second = event(setup)
    assert not first["duplicate"] and second["duplicate"]
    assert set(r[0] for r in rows(db, "SELECT user_id FROM push_jobs")) == {owner, member}
    assert rows(db, "SELECT COUNT(*) FROM push_messages") == [(1,)]


@pytest.mark.parametrize(
    "change", ["revoked", "disabled", "token_rotated", "signed_out", "account_switched"]
)
def test_queued_delivery_rechecks_current_authority(setup, change):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    event(setup)
    job = None
    while True:
        claimed = push.claim()
        if claimed is None:
            break
        if claimed[1] == ids[member]:
            job = claimed
            break
        push.finish(claimed, "accepted")
    assert job
    if change == "revoked":
        homes.change_member(home, owner, member)
    elif change == "disabled":
        with sqlite3.connect(db) as c:
            c.execute("UPDATE users SET active=0 WHERE id=?", (member,))
    elif change == "token_rotated":
        push.register(member, ids[member], "a" * 64, "rotated_" + "x" * 40)
    elif change == "account_switched":
        push.register(outsider, ids[member], "a" * 64, "token_" + "1" * 40)
    else:
        binding = rows(db, "SELECT binding FROM installations WHERE id='" + ids[member] + "'")[0][0]
        push.unregister(member, ids[member], "a" * 64, binding)
    assert push.authorized(job) is None
    assert rows(db, "SELECT state FROM push_jobs WHERE installation_id='" + ids[member] + "'") == [
        ("cancelled",)
    ]


def test_installation_proof_prevents_takeover_and_token_cannot_bind_twice(setup):
    _, _, _, push, owner, member, _, _, _, ids, _ = setup
    with pytest.raises(APIError):
        push.register(member, ids[owner], "b" * 64, "new_" + "x" * 40)
    with pytest.raises(APIError):
        push.register(member, str(uuid.uuid4()), "b" * 64, "token_" + "0" * 40)
    before = push.register(owner, ids[owner], "a" * 64, "token_" + "0" * 40)["binding"]
    after = push.register(owner, ids[owner], "a" * 64, "token_" + "0" * 40)["binding"]
    assert before == after


def test_stale_unregister_and_provider_response_do_not_disable_rotated_binding(setup):
    db, _, _, push, owner, *_ = setup
    ids = setup[9]
    old = push.register(owner, ids[owner], "a" * 64, "token_" + "0" * 40)["binding"]
    push.test(setup[7], owner, ids[owner])
    job = push.claim()
    push.register(owner, ids[owner], "a" * 64, "rotated_" + "x" * 40)
    assert push.unregister(owner, ids[owner], "a" * 64, old)["status"] == "stale_binding_ignored"
    push.finish(job, "unregistered")
    assert rows(db, "SELECT active FROM installations WHERE id='" + ids[owner] + "'") == [(1,)]


def test_restart_recovers_lease_retry_is_delayed_and_expired_jobs_cancel(setup):
    db, now, _, push, owner, *_ = setup
    ids = setup[9]
    push.test(setup[7], owner, ids[owner])
    job = push.claim()
    other = PushStore(db, clock=lambda: now[0])
    assert other.claim() is None
    now[0] += 61
    assert other.claim() == job
    other.finish(job, "retry", retry_after=30)
    assert other.claim() is None
    now[0] += 31
    assert other.claim() == job
    other.finish(job, "retry")
    now[0] += 301
    assert other.claim() is None
    assert rows(db, "SELECT state,last_error FROM push_jobs") == [("cancelled", "expired")]


def test_worker_never_sends_sensor_payload_or_outsider_token(setup):
    _, _, _, push, owner, member, outsider, *_ = setup
    event(setup)
    sent = []

    class Sender:
        def send(self, recipient):
            sent.append(recipient)
            return "accepted", 0

    worker = PushWorker(push, Sender())
    while worker.once():
        pass
    assert {r["subject"] for r in sent} == {"owner", "member"}
    assert all("payload" not in r and "private" not in str(r) for r in sent)


def test_test_notification_targets_only_requesting_owner_and_rate_limits(setup):
    db, _, _, push, owner, member, outsider, home, other, ids, _ = setup
    with pytest.raises(APIError):
        push.test(home, member, ids[member])
    with pytest.raises(APIError):
        push.test(home, outsider, ids[outsider])
    with pytest.raises(APIError):
        push.test(home, owner, ids[member])
    assert push.test(home, owner, ids[owner])["queued"] == 1
    assert rows(db, "SELECT user_id FROM push_jobs") == [(owner,)]
    with pytest.raises(APIError) as caught:
        push.test(home, owner, ids[owner])
    assert caught.value.status == 429


def test_schema_two_migration_preserves_identity_and_registered_home(tmp_path):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as c:
        c.execute(
            "CREATE TABLE runtime_metadata(id INTEGER PRIMARY KEY,"
            "installation_id TEXT,created_at TEXT)"
        )
        c.execute("INSERT INTO runtime_metadata VALUES(1,'keep-runtime','keep-created')")
        for statement in STATEMENTS:
            c.execute(statement)
        c.execute("INSERT INTO users VALUES('u','i','s','e',1)")
        c.execute("INSERT INTO homes VALUES('h','keep-home','u')")
        c.execute("INSERT INTO memberships VALUES('h','u','owner',1,NULL)")
        c.execute("PRAGMA user_version=2")
    initialize(db)
    initialize(db)
    assert rows(db, "PRAGMA user_version") == [(3,)]
    assert rows(db, "SELECT installation_id FROM runtime_metadata") == [("keep-runtime",)]
    assert rows(db, "SELECT name FROM homes") == [("keep-home",)]
    assert rows(db, "PRAGMA integrity_check") == [("ok",)]
