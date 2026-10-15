"""Abuse bounds: hub rate limit, per-home retention and queue caps, account quotas, parser hardening."""

import logging
import sqlite3
import sys
import time
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'services/central-server'))
import central_server.households as households_module
import central_server.push as push_module
from central_server.control import Controls
from central_server.households import APIError
from central_server.limits import Limiter
from central_server.web import create_app

from tests.test_central_households import environment as environment
from tests.test_central_push import setup as setup

JSON = {'Content-Type': 'application/json'}


def rows(db, sql, *params):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


def test_limiter_enforces_every_window_and_recovers_with_time():
    clock = [0.0]
    limiter = Limiter((3, 60), (5, 86400), clock=lambda: clock[0])
    assert [limiter.take('hub') for _ in range(3)] == [0, 0, 0]
    assert limiter.take('hub') == 20 and limiter.take('other') == 0  # keys are independent
    clock[0] += 20
    assert limiter.take('hub') == 0  # the minute window refilled one token
    clock[0] += 60
    assert limiter.take('hub') == 0
    assert 17000 < limiter.take('hub') <= 17280  # five per day used: wait for the daily window
    clock[0] += 86400
    assert limiter.take('hub') == 0


def test_limiter_drops_idle_keys_after_refill_and_stays_bounded():
    clock = [0.0]
    limiter = Limiter((60, 60), clock=lambda: clock[0])
    for index in range(1100):
        limiter.take('client' + str(index))
    assert len(limiter.buckets) == Limiter.MAX_KEYS  # every key busy: the oldest ones were dropped
    clock[0] += 10 * 86400
    limiter.take('fresh')
    assert set(limiter.buckets) == {'fresh'}  # idle buckets are refilled before the full check


def test_hub_event_flood_is_limited_per_hub_without_starving_other_homes(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    second = homes.provision_hub()
    homes.claim(other, outsider, second['claim_code'])
    app = create_app(db)
    clock = [0.0]
    app.extensions['limits']['hub_events'].clock = lambda: clock[0]
    client = app.test_client()

    def send(token, index):
        return client.post('/v1/hub/events', json={'event_id': 'e' + str(index), 'kind': 'sensor.open', 'payload': {}},
                           headers={'Authorization': 'Bearer ' + token})
    assert all(send(hub['hub_token'], i).status_code == 200 for i in range(120))
    limited = send(hub['hub_token'], 120)
    assert limited.status_code == 429 and limited.json == {'error': 'rate_limited'}
    assert int(limited.headers['Retry-After']) >= 1
    assert rows(db, 'SELECT COUNT(*) FROM events WHERE home_id=?', home) == [(120,)]
    assert send(second['hub_token'], 0).status_code == 200  # the other home's hub is unaffected
    clock[0] += 1
    assert send(hub['hub_token'], 121).status_code == 200
    bogus = client.post('/v1/hub/events', json={'event_id': 'x', 'kind': 'sensor.open', 'payload': {}},
                        headers={'Authorization': 'Bearer hub_' + 'x' * 43})
    assert bogus.status_code == 401  # unauthenticated requests never create buckets
    assert set(app.extensions['limits']['hub_events'].buckets) == {hub['hub_id'], second['hub_id']}


def test_event_retention_keeps_newest_per_home_and_drops_their_push_rows(setup, monkeypatch):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    monkeypatch.setattr(households_module, 'EVENT_RETENTION', 3)
    second = homes.provision_hub()
    homes.claim(other, outsider, second['claim_code'])
    homes.ingest(second['hub_token'], 'keep-other', 'sensor.open', {})
    kept = [homes.ingest(hub['hub_token'], 'e' + str(i), 'sensor.open', {'i': i})['id'] for i in range(6)]
    assert [r[0] for r in rows(db, 'SELECT id FROM events WHERE home_id=? ORDER BY id', home)] == kept[3:]
    assert rows(db, 'SELECT COUNT(*) FROM events WHERE home_id=?', other) == [(1,)]
    assert rows(db, 'SELECT COUNT(*) FROM push_messages WHERE event_id IN (?,?,?)', *kept[:3]) == [(0,)]
    assert rows(db, 'SELECT COUNT(*) FROM push_jobs j JOIN push_messages p ON p.id=j.message_id '
                    'WHERE p.home_id=?', home) == [(6,)]
    assert rows(db, 'PRAGMA foreign_key_check') == [] and rows(db, 'PRAGMA integrity_check') == [('ok',)]
    assert homes.ingest(hub['hub_token'], 'e5', 'sensor.open', {'i': 5})['duplicate']
    assert len(homes.events(home, owner)) == 3


def test_heartbeat_replaces_device_rows_instead_of_accumulating(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    control = Controls(db, clock=lambda: now[0])
    for index in range(30):
        control.heartbeat(hub['hub_token'], [{'id': format(index, '032x'), 'name': 'Unit ' + str(index)}])
    assert rows(db, 'SELECT device_id,active FROM control_devices WHERE hub_id=?', hub['hub_id']) == [
        (format(29, '032x'), 1)]
    control.heartbeat(hub['hub_token'], [{'id': format(i, '032x'), 'name': 'U'} for i in range(20)])
    assert rows(db, 'SELECT COUNT(*) FROM control_devices') == [(20,)]
    control.heartbeat(hub['hub_token'], [])
    assert rows(db, 'SELECT COUNT(*) FROM control_devices') == [(0,)]
    assert control.status(home, owner)['devices'] == []


def test_pending_push_jobs_per_home_are_capped_oldest_first(setup, monkeypatch, caplog):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    monkeypatch.setattr(push_module, 'PENDING_JOBS_PER_HOME', 3)
    events = []
    with caplog.at_level(logging.WARNING):
        for index in range(3):
            now[0] += 1
            events.append(homes.ingest(hub['hub_token'], 'e' + str(index), 'sensor.open', {})['id'])
    pending = rows(db, "SELECT p.event_id FROM push_jobs j JOIN push_messages p ON p.id=j.message_id "
                       "WHERE j.state='pending'")
    assert len(pending) == 3 and [r[0] for r in pending].count(events[2]) == 2  # newest event intact
    assert events[0] not in [r[0] for r in pending]
    assert 'PUSH_QUEUE_CAPPED' in caplog.text and home not in caplog.text and ids[owner] not in caplog.text


def test_worker_alternates_between_homes_so_one_flooding_home_cannot_starve_another(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    second = homes.provision_hub()
    homes.claim(other, outsider, second['claim_code'])
    for index in range(4):
        now[0] += 1
        homes.ingest(hub['hub_token'], 'a' + str(index), 'sensor.open', {})  # two jobs each, older
    now[0] += 1
    homes.ingest(second['hub_token'], 'b0', 'sensor.open', {})  # one job, newest
    served = []
    while job := push.claim():
        served.append(rows(db, 'SELECT home_id FROM push_messages WHERE id=?', job[0])[0][0])
        push.finish(job, 'accepted')
    assert served[:2] == [home, other]  # the other home is served second, not after the flood
    assert served.count(home) == 8 and served.count(other) == 1


def test_home_and_invitation_quotas_count_active_rows_only(environment, monkeypatch):
    monkeypatch.setattr(households_module, 'HOMES_PER_USER', 2)
    monkeypatch.setattr(households_module, 'OPEN_INVITATIONS_PER_HOME', 2)
    _, app, _, _, call = environment
    first = call('a', 'POST', '/v1/homes', {'name': 'one'}).json['id']
    assert call('a', 'POST', '/v1/homes', {'name': 'two'}).status_code == 201
    denied = call('a', 'POST', '/v1/homes', {'name': 'three'})
    assert denied.status_code == 429 and denied.json == {'error': 'quota_exceeded'}
    assert call('b', 'POST', '/v1/homes', {'name': 'b-one'}).status_code == 201  # per account
    assert call('a', 'DELETE', '/v1/homes/' + first, {'confirmation_name': 'one'}).status_code == 200
    home = call('a', 'POST', '/v1/homes', {'name': 'three'}).json['id']

    def invite(who):
        return call('a', 'POST', f'/v1/homes/{home}/invitations', {'email': who + '@example.test', 'role': 'viewer'})
    tokens = [invite('x').json['invitation_token'], invite('y').json['invitation_token']]
    denied = invite('z')
    assert denied.status_code == 429 and denied.json == {'error': 'quota_exceeded'}
    assert call('x', 'POST', '/v1/invitations/accept', {'invitation_token': tokens[0]}).status_code == 200
    assert invite('z').status_code == 201  # consumed invitations no longer count
    app.extensions['households'].clock = lambda: time.time() + 86401
    assert invite('w').status_code == 201  # expired ones neither


def test_installation_rows_per_account_are_bounded_and_stale_rows_pruned(setup, monkeypatch):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    monkeypatch.setattr(push_module, 'INSTALLATION_ROWS_PER_USER', 3)
    push.set_preferences(owner, ids[owner], 'a' * 64,
                         dict(door=False, climate=False, warning=False, climate_interval_minutes=5))
    binding = rows(db, 'SELECT binding FROM installations WHERE id=?', ids[owner])[0][0]
    push.unregister(owner, ids[owner], 'a' * 64, binding)
    extra = [str(uuid.uuid4()) for _ in range(3)]
    for index, installation in enumerate(extra):
        now[0] += 1
        push.register(owner, installation, 'c' * 64, 'extra_' + str(index) * 40)
    # The fourth row for this account evicts the signed-out one instead of growing without bound.
    assert rows(db, 'SELECT COUNT(*) FROM installations WHERE user_id=?', owner) == [(3,)]
    assert rows(db, 'SELECT COUNT(*) FROM installations WHERE id=?', ids[owner]) == [(0,)]
    assert rows(db, 'SELECT COUNT(*) FROM notification_preferences WHERE installation_id=?', ids[owner]) == [(0,)]
    with pytest.raises(APIError) as caught:  # every row active: nothing can be reused
        push.register(owner, str(uuid.uuid4()), 'd' * 64, 'full_' + 'x' * 40)
    assert caught.value.code == 'quota_exceeded' and caught.value.status == 429
    assert push.register(member, str(uuid.uuid4()), 'd' * 64, 'full_' + 'x' * 40)['status'] == 'registered'
    push.unregister(owner, extra[0], 'c' * 64, rows(db, 'SELECT binding FROM installations WHERE id=?', extra[0])[0][0])
    now[0] += 29 * 86400
    push.prune()
    assert rows(db, 'SELECT COUNT(*) FROM installations WHERE id=?', extra[0]) == [(1,)]
    now[0] += 2 * 86400
    push.prune()
    assert rows(db, 'SELECT COUNT(*) FROM installations WHERE id=?', extra[0]) == [(0,)]
    assert rows(db, 'SELECT COUNT(*) FROM installations WHERE user_id=?', owner) == [(2,)]
    assert rows(db, 'PRAGMA foreign_key_check') == []


def test_prune_deletes_long_expired_invitations_only(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    homes.invitation(home, owner, 'late@example.test', 'viewer')
    now[0] += 30 * 86400  # expired, but inside the 30-day diagnostic window
    push.prune()
    assert rows(db, 'SELECT COUNT(*) FROM invitations') == [(2,)]
    now[0] += 2 * 86400
    push.prune()
    assert rows(db, 'SELECT COUNT(*) FROM invitations') == [(0,)]


def test_deeply_nested_body_is_a_json_error_and_hub_routes_authenticate_first(environment):
    _, app, _, token, call = environment
    client = app.test_client()
    nested = '[' * 8000 + ']' * 8000  # within the 16 KiB body cap; json.loads raises RecursionError
    user = client.post('/v1/homes', data=nested, headers=JSON | {'Authorization': 'Bearer ' + token('a')})
    assert user.status_code == 400 and user.json == {'error': 'invalid_body'}
    for path, method in (('/v1/hub/events', 'POST'), ('/v1/hub/control/status', 'PUT'),
                         ('/v1/hub/inventory', 'PUT'),
                         ('/v1/hub/control/next', 'POST'), ('/v1/hub/control/x/result', 'POST')):
        anonymous = client.open(path, method=method, data=nested, headers=JSON)
        assert anonymous.status_code == 401 and anonymous.json == {'error': 'invalid_credentials'}
        forged = client.open(path, method=method, data=nested,
                             headers=JSON | {'Authorization': 'Bearer hub_' + 'x' * 43})
        assert forged.status_code == 401 and forged.json == {'error': 'invalid_hub_credentials'}
    home = call('a', 'POST', '/v1/homes', {'name': 'A'}).json['id']
    hub = app.extensions['households'].provision_hub()
    assert call('a', 'POST', f'/v1/homes/{home}/hubs/claim', {'claim_code': hub['claim_code']}).status_code == 200
    real = client.post('/v1/hub/events', data=nested, headers=JSON | {'Authorization': 'Bearer ' + hub['hub_token']})
    assert real.status_code == 400 and real.json == {'error': 'invalid_body'}


def test_huge_integer_expiry_is_rejected_not_a_server_error(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    for expiry in (10**400, -10**400, 2**53 + 1, -(2**53) - 1):
        with pytest.raises(APIError) as caught:
            homes.ingest(hub['hub_token'], 'huge', 'sensor.open', {'notification_expires_at': expiry})
        assert caught.value.code == 'invalid_notification_expiry' and caught.value.status == 400
    response = create_app(db).test_client().post(
        '/v1/hub/events', headers=JSON | {'Authorization': 'Bearer ' + hub['hub_token']},
        data='{"event_id":"huge","kind":"sensor.open","payload":{"notification_expires_at":' + '9' * 400 + '}}')
    assert response.status_code == 400 and response.json == {'error': 'invalid_notification_expiry'}
    assert rows(db, 'SELECT COUNT(*) FROM events') == [(0,)]


def test_slightly_future_issue_times_are_tolerated_but_expiry_stays_strict(environment):
    _, _, verifier, token, _ = environment
    now = int(time.time())
    assert verifier.verify(token('owner', iat=now + 30, auth_time=now + 30)).subject == 'owner'
    for changes in (dict(iat=now + 120), dict(auth_time=now + 120), dict(exp=now - 1)):
        with pytest.raises(APIError) as caught:
            verifier.verify(token('owner', **changes))
        assert caught.value.status == 401


@pytest.mark.parametrize('name', ['‮emoh', 'home​', 'ho\x7fme', 'ho\x85me', '﻿home', 'home\n'])
def test_control_and_format_characters_are_rejected_in_text_fields(environment, name):
    _, _, _, _, call = environment
    response = call('a', 'POST', '/v1/homes', {'name': name})
    assert response.status_code == 400 and response.json == {'error': 'invalid_body'}


def test_ordinary_names_pass_and_hub_device_names_are_cleaned_not_refused(environment):
    _, app, _, _, call = environment
    assert call('a', 'POST', '/v1/homes', {'name': '우리 집 – café №2'}).status_code == 201
    home = call('a', 'POST', '/v1/homes', {'name': 'A'}).json['id']
    hub = app.extensions['households'].provision_hub()
    call('a', 'POST', f'/v1/homes/{home}/hubs/claim', {'claim_code': hub['claim_code']})
    client = app.test_client()
    headers = {'Authorization': 'Bearer ' + hub['hub_token']}

    def beat(name):
        return client.put('/v1/hub/control/status', json={'devices': [{'id': 'c' * 32, 'name': name}]}, headers=headers)
    assert beat('‮Living​ room\x7f').status_code == 200
    assert call('a', 'GET', f'/v1/homes/{home}/control').json['devices'] == [{'id': 'c' * 32, 'name': 'Living room'}]
    assert beat(7).status_code == 400 and beat('​').status_code == 400


def test_token_takeover_is_limited_to_same_account_signed_out_or_stale_holders(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    homes.ingest(hub['hub_token'], 'door', 'sensor.open', {})
    job = None
    while claimed := push.claim():
        if claimed[1] == ids[owner]:
            job = claimed
            break
        push.finish(claimed, 'accepted')
    assert job
    with pytest.raises(APIError) as caught:  # a stranger cannot silence a live phone
        push.register(outsider, str(uuid.uuid4()), 'e' * 64, 'token_' + '0' * 40)
    assert caught.value.code == 'installation_conflict' and caught.value.status == 409
    assert rows(db, 'SELECT active FROM installations WHERE id=?', ids[owner]) == [(1,)]
    assert push.authorized(job)['token'] == 'token_' + '0' * 40
    second = str(uuid.uuid4())  # the same account's reinstalled app brings its token along
    assert push.register(owner, second, 'f' * 64, 'token_' + '0' * 40)['status'] == 'registered'
    assert rows(db, 'SELECT token,active FROM installations WHERE id=?', ids[owner]) == [(None, 0)]
    assert push.authorized(job) is None  # never redirected to the new holder of the token
    assert rows(db, 'SELECT state FROM push_jobs WHERE installation_id=?', ids[owner]) == [('cancelled',)]
    now[0] += 31 * 86400  # a holder silent for 30 days may be replaced by anyone
    stolen = str(uuid.uuid4())
    assert push.register(outsider, stolen, 'e' * 64, 'token_' + '0' * 40)['status'] == 'registered'
    assert rows(db, 'SELECT token,active FROM installations WHERE id=?', second) == [(None, 0)]
    with sqlite3.connect(db) as conn:  # a signed-out holder that still carries the token
        conn.execute('UPDATE installations SET active=0,updated_at=? WHERE id=?', (now[0], stolen))
    assert push.register(member, str(uuid.uuid4()), 'g' * 64, 'token_' + '0' * 40)['status'] == 'registered'
    assert rows(db, 'SELECT token FROM installations WHERE id=?', stolen) == [(None,)]
