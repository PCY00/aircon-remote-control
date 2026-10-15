"""Control delivery at the expiry boundary and stable JSON errors for unmatched hub results."""

import uuid

from tests.test_central_push import setup as setup
from central_server.control import Controls
from central_server.web import create_app

DEVICE = 'b'*32


def test_next_never_dispatches_nonpositive_remaining(setup):
    db, now, _, _, owner, _, _, home, _, _, hub = setup
    step = [0.0]
    def clock():
        now[0] += step[0]
        return now[0]
    control = Controls(db, clock=clock)
    control.heartbeat(hub['hub_token'], [{'id': DEVICE, 'name': 'Test air conditioner'}])
    command = control.enqueue(home, owner, str(uuid.uuid4()), DEVICE, 'power_off')
    # Every clock read advances past the deadline; the first read is still just before it.
    now[0], step[0] = command['expires_at']-0.00015, 0.0001
    delivered = control.next(hub['hub_token'])['command']
    step[0] = 0.0
    state = control.command(home, owner, command['id'])['state']
    if delivered is None:
        assert state == 'expired'
    else:
        assert delivered['remaining_seconds'] > 0 and state == 'dispatched'


def test_unmatched_result_reports_are_stable_json_errors(setup):
    db, now, homes, _, owner, _, _, home, _, _, hub = setup
    control = Controls(db, clock=lambda: now[0])
    control.heartbeat(hub['hub_token'], [{'id': DEVICE, 'name': 'Test air conditioner'}])
    command = control.enqueue(home, owner, str(uuid.uuid4()), DEVICE, 'power_off')
    delivered = control.next(hub['hub_token'])['command']
    client = create_app(db).test_client()
    def report(token, command_id, attempt, state='sent'):
        return client.post('/v1/hub/control/'+command_id+'/result', json={'attempt_token': attempt, 'state': state},
                           headers={'Authorization': 'Bearer '+token})
    for command_id, attempt in ((command['id'], 'f'*64), (str(uuid.uuid4()), delivered['attempt_token'])):
        response = report(hub['hub_token'], command_id, attempt)
        assert response.status_code == 404 and response.json == {'error': 'not_found'}
    assert report(hub['hub_token'], command['id'], delivered['attempt_token']).json == {'status': 'recorded'}
    response = report(hub['hub_token'], command['id'], delivered['attempt_token'], 'failed')
    assert response.status_code == 409 and response.json == {'error': 'control_result_conflict'}
    # After a re-link the old hub's receipt can never match the new hub.
    homes.revoke_hub(home, owner, hub['hub_id'])
    replacement = homes.provision_hub()
    homes.claim(home, owner, replacement['claim_code'])
    response = report(replacement['hub_token'], command['id'], delivered['attempt_token'])
    assert response.status_code == 404 and response.json == {'error': 'not_found'}
    response = report(hub['hub_token'], command['id'], delivered['attempt_token'])
    assert response.status_code == 401 and response.json == {'error': 'invalid_hub_credentials'}


def test_lone_surrogate_in_heartbeat_name_is_stripped_not_a_500(setup):
    db, now, homes, _, owner, _, _, home, _, _, hub = setup
    client = create_app(db).test_client()
    # Raw JSON escape \ud800 decodes to a lone surrogate that SQLite cannot encode as UTF-8.
    body = '{"devices": [{"id": "' + DEVICE + '", "name": "\\ud800거실 에어컨"}]}'
    response = client.put("/v1/hub/control/status", data=body.encode(), content_type='application/json',
                          headers={'Authorization': 'Bearer '+hub['hub_token']})
    assert response.status_code == 200 and response.json == {'status': 'ready'}
    assert Controls(db, clock=lambda: now[0]).status(home, owner)['devices'] == [
        {'id': DEVICE, 'name': '거실 에어컨'}]
    body = '{"devices": [{"id": "' + DEVICE + '", "name": "\\udfff"}]}'
    response = client.put("/v1/hub/control/status", data=body.encode(), content_type='application/json',
                          headers={'Authorization': 'Bearer '+hub['hub_token']})
    assert response.status_code == 400 and response.json == {'error': 'invalid_body'}
