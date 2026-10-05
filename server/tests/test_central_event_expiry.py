"""An offline Pi must not refresh an already expired alert when reconnecting."""

import sqlite3

import pytest

from tests.test_central_push import setup as setup


def test_source_expiry_survives_relay_delay_and_event_deduplication(setup):
    db, now, homes, push, *_, hub = setup
    payload = {"notification_expires_at": 1100.0}
    first = homes.ingest(hub["hub_token"], "source-event", "sensor.door_changed", payload)
    now[0] = 1060
    assert homes.ingest(hub["hub_token"], "source-event", "sensor.door_changed", payload)[
        "duplicate"
    ]
    with sqlite3.connect(db) as conn:
        assert (
            conn.execute(
                "SELECT expires_at FROM push_messages WHERE event_id=?", (first["id"],)
            ).fetchone()[0]
            == 1100
        )
        assert conn.execute("SELECT COUNT(*) FROM push_messages").fetchone()[0] == 1
    now[0] = 1100
    assert push.claim() is None


def test_expired_event_can_be_recorded_without_notifying_a_family(setup):
    db, now, homes, push, *_, hub = setup
    homes.ingest(
        hub["hub_token"],
        "old-event",
        "sensor.door_changed",
        {"notification_expires_at": now[0] - 1},
    )
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM push_jobs").fetchone()[0] == 0
    assert push.claim() is None


@pytest.mark.parametrize("expiry", [True, "future", None, float("inf"), float("nan"), 1301])
def test_invalid_or_extended_expiry_is_rejected_before_recording(setup, expiry):
    from central_server.households import APIError

    db, _, homes, _, *_, hub = setup
    with pytest.raises(APIError) as error:
        homes.ingest(
            hub["hub_token"],
            "invalid-event",
            "sensor.door_changed",
            {"notification_expires_at": expiry},
        )
    assert error.value.status == 400
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
