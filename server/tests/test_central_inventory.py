"""Hub device list: strict shape, forward-compatible names, whole-list replacement and privacy."""

import json
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'services/central-server'))
from central_server.control import Controls
from central_server.households import APIError
from central_server.inventory import BODY_BYTES, Inventory, validate

from tests.test_central_households import environment as environment
from tests.test_central_push import setup as setup

JSON = {'Content-Type': 'application/json'}
KEYS = {'id', 'name', 'room', 'type', 'capabilities', 'state', 'reported_at', 'controllable'}


def device(index=0, **changes):
    return {'id': format(index, '032x'), 'name': '현관문', 'room': '현관', 'type': 'door_sensor',
            'capabilities': ['contact', 'battery'], 'state': {'contact': 'closed', 'battery_percent': 87},
            'reported_at': time.time() - 60, 'controllable': False} | changes


def rows(db, sql, *params):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql, params).fetchall()


@pytest.fixture
def house(environment):
    db, app, _, _, call = environment
    home = call('owner', 'POST', '/v1/homes', {'name': 'A'}).json['id']
    for person in ('viewer', 'member'):
        invite = call('owner', 'POST', f'/v1/homes/{home}/invitations',
                      {'email': person + '@example.test', 'role': person}).json['invitation_token']
        assert call(person, 'POST', '/v1/invitations/accept', {'invitation_token': invite}).status_code == 200
    hub = app.extensions['households'].provision_hub()
    assert call('owner', 'POST', f'/v1/homes/{home}/hubs/claim', {'claim_code': hub['claim_code']}).status_code == 200
    client = app.test_client()

    def put(value=None, *, raw=None, token=hub['hub_token']):
        headers = JSON | {'Authorization': 'Bearer ' + token}
        data = raw if raw is not None else json.dumps(value, ensure_ascii=False).encode()
        return client.put('/v1/hub/inventory', data=data, headers=headers)

    def listing(person='viewer', target=home):
        return call(person, 'GET', f'/v1/homes/{target}/devices')
    return SimpleNamespace(db=db, app=app, call=call, home=home, hub=hub, put=put, listing=listing)


def test_whole_list_is_replaced_in_sent_order_and_readable_by_viewers(house):
    first = [device(2), device(0, name='거실 에어컨', type='air_conditioner', controllable=True,
                                capabilities=['power', 'setpoint', 'mode', 'fan', 'actions'],
                                state={'power': 'on', 'setpoint_c': 24, 'inferred': True}),
             device(1, type='climate_sensor', state={'temperature_c': 24.5, 'battery_low': False})]
    response = house.put({'devices': first})
    assert response.status_code == 200 and response.json == {'status': 'stored', 'count': 3}
    for person in ('owner', 'member', 'viewer'):
        listed = house.listing(person)
        assert listed.status_code == 200 and set(listed.json) == {'devices', 'updated_at', 'hub_online'}
    body = house.listing().json
    assert [item['id'] for item in body['devices']] == [format(i, '032x') for i in (2, 0, 1)]
    assert all(set(item) == KEYS for item in body['devices'])
    assert body['devices'][1] == {**first[1], 'reported_at': float(first[1]['reported_at'])}
    assert isinstance(body['updated_at'], float) and body['hub_online'] is False
    assert house.put({'devices': [device(1, name='새 이름')]}).json['count'] == 1
    assert [(item['id'], item['name']) for item in house.listing().json['devices']] == [(format(1, '032x'), '새 이름')]
    assert house.put({'devices': []}).status_code == 200
    emptied = house.listing().json
    assert emptied['devices'] == [] and emptied['updated_at'] is not None
    assert rows(house.db, 'SELECT COUNT(*) FROM hub_devices') == [(0,)]


def test_homes_without_hub_or_list_and_outsiders(house):
    call = house.call
    assert house.listing().json == {'devices': [], 'updated_at': None, 'hub_online': False}
    assert house.listing('outsider').status_code == 404
    other = call('outsider', 'POST', '/v1/homes', {'name': 'B'}).json['id']
    assert house.listing('outsider', other).json == {'devices': [], 'updated_at': None, 'hub_online': False}
    assert house.listing('owner', other).status_code == 404
    house.put({'devices': [device()]})
    assert house.listing('outsider', other).json['devices'] == []  # one home's list never leaks
    assert call('owner', 'GET', f'/v1/homes/{house.home}/devices',
                email_verified=False).status_code == 401


@pytest.mark.parametrize('change', [
    dict(id='A' * 32), dict(id='a' * 31), dict(id='g' * 32), dict(id=7),
    dict(name=''), dict(name='   '), dict(name='가' * 81), dict(name=None), dict(name='\u200b'),
    dict(room='가' * 41), dict(room=None),
    dict(type='Door'), dict(type='1door'), dict(type='door-sensor'), dict(type='a' * 33), dict(type=''),
    dict(type=None), dict(capabilities='contact'), dict(capabilities=['contact', 'contact']),
    dict(capabilities=['c' + str(i) for i in range(17)]), dict(capabilities=['Contact']),
    dict(capabilities=[5]), dict(capabilities=[['contact']]), dict(state=[]), dict(state=None),
    dict(state={'k' + str(i): 1 for i in range(17)}), dict(state={'Battery': 1}),
    dict(state={'battery percent': 1}), dict(state={'nested': {}}), dict(state={'list': []}),
    dict(state={'text': 'x' * 41}), dict(state={'text': 'open\u202e'}), dict(state={'text': 'a\nb'}),
    dict(state={'number': 1e9 + 1}), dict(state={'number': -1e10}), dict(state={'number': 10 ** 12}),
    dict(reported_at=time.time() + 400), dict(reported_at=True), dict(reported_at='1'),
    dict(reported_at=-1), dict(reported_at=2 ** 60), dict(controllable=1), dict(controllable=None),
])
def test_each_device_rule_refuses_the_whole_report(house, change):
    house.put({'devices': [device(9)]})
    response = house.put({'devices': [device(), device(1) | change]})
    assert response.status_code == 400 and response.json == {'error': 'invalid_body'}
    assert [item['id'] for item in house.listing().json['devices']] == [format(9, '032x')]


RAW = json.dumps(device(reported_at=None, state={'contact': 'closed', 'value': 424242})).encode()


@pytest.mark.parametrize('raw', [
    b'[]', b'{"devices": {}}', b'{"devices": null}', b'{"devices": [], "extra": 1}', b'{}', b'not json',
    b'{"devices": [' + RAW[:-1] + b', "extra": 1}]}',
    b'{"devices": [' + RAW.replace(b'"room": "\\ud604\\uad00", ', b'') + b']}',
    *(b'{"devices": [' + RAW.replace(b'424242', number) + b']}'
      for number in (b'NaN', b'Infinity', b'-Infinity', b'1e400', b'9' * 400)),
    b'{"devices": [' + RAW.replace(b'closed', b'\\ud800') + b']}',
])
def test_malformed_bodies_and_non_finite_numbers_are_invalid(house, raw):
    response = house.put(raw=raw)
    assert response.status_code == 400 and response.json == {'error': 'invalid_body'}


def test_duplicate_ids_and_more_than_fifty_devices_are_refused(house):
    assert house.put({'devices': [device(1), device(1, name='twin')]}).status_code == 400
    assert house.put({'devices': [device(i) for i in range(51)]}).status_code == 400
    response = house.put({'devices': [device(i) for i in range(50)]})
    assert response.status_code == 200 and response.json['count'] == 50


def test_unknown_but_well_formed_blocks_are_kept_and_hidden_characters_stripped(house):
    future = device(name='\u202e현관\u200b문\x7f', room='\u200b', type='leak_sensor_v2',
                    capabilities=['future_block', 'z' * 32] + ['c' + str(i) for i in range(14)],
                    state={'co2_ppm': 900, 'flag': None, 'on': True, 'off': False, 'tiny': -1e9,
                           'huge': 1e9, 'half': 0.5, 'empty': '', 'label': 'x' * 40, 'zero': 0,
                           **{'k' + str(i): i for i in range(6)}},
                    reported_at=None, controllable=True)
    padded = device(1, name='  ' + '가' * 80 + '  ', room=' ' + '나' * 40 + ' ',
                    reported_at=int(time.time()) + 200, capabilities=[], state={})
    assert house.put({'devices': [future, padded]}).status_code == 200
    stored, second = house.listing().json['devices']
    assert (stored['name'], stored['room'], stored['type']) == ('현관문', '', 'leak_sensor_v2')
    assert stored['capabilities'] == future['capabilities'] and stored['state'] == future['state']
    assert stored['reported_at'] is None and stored['controllable'] is True
    assert (second['name'], second['room']) == ('가' * 80, '나' * 40)
    assert second['reported_at'] == float(padded['reported_at']) and second['state'] == {}


def test_body_cap_is_32_kib_here_and_16_kib_everywhere_else(house):
    devices = [device(i, name='가' * 80, room='나' * 40) for i in range(50)]
    body = json.dumps({'devices': devices}, ensure_ascii=False).encode()
    assert 16384 < len(body) < BODY_BYTES == 32768  # beyond the app-wide cap, inside this route's
    exact = body + b' ' * (BODY_BYTES - len(body))
    assert house.put(raw=exact).status_code == 200
    over = house.put({'devices': []}, raw=exact + b' ')
    assert over.status_code == 413 and over.json == {'error': 'body_too_large'}
    assert len(house.listing().json['devices']) == 50  # the refused report changed nothing
    event = b'{"event_id":"big","kind":"sensor.open","payload":{}}'
    big = house.app.test_client().post('/v1/hub/events', data=event + b' ' * (16385 - len(event)),
                                       headers=JSON | {'Authorization': 'Bearer ' + house.hub['hub_token']})
    assert big.status_code == 413  # other routes keep the existing 16 KiB limit
    assert rows(house.db, 'SELECT COUNT(*) FROM events') == [(0,)]


def test_inventory_is_rate_limited_per_hub(house):
    clock = [0.0]
    limiter = house.app.extensions['limits']['hub_inventory']
    limiter.clock = lambda: clock[0]
    second = house.app.extensions['households'].provision_hub()
    other = house.call('outsider', 'POST', '/v1/homes', {'name': 'B'}).json['id']
    house.call('outsider', 'POST', f'/v1/homes/{other}/hubs/claim', {'claim_code': second['claim_code']})
    assert all(house.put({'devices': [device()]}).status_code == 200 for _ in range(12))
    limited = house.put({'devices': [device()]})
    assert limited.status_code == 429 and limited.json == {'error': 'rate_limited'}
    assert int(limited.headers['Retry-After']) >= 1
    assert house.put({'devices': []}, token=second['hub_token']).status_code == 200
    assert house.put({'devices': []}, token='hub_' + 'x' * 43).status_code == 401
    assert set(limiter.buckets) == {house.hub['hub_id'], second['hub_id']}  # strangers make no bucket
    clock[0] += 5
    assert house.put({'devices': []}).status_code == 200


def test_revoked_hub_and_deleted_home_take_names_and_rooms_with_them(house):
    call = house.call
    assert house.put({'devices': [device(), device(1)]}).status_code == 200
    second = house.app.extensions['households'].provision_hub()
    other = call('outsider', 'POST', '/v1/homes', {'name': 'B'}).json['id']
    call('outsider', 'POST', f'/v1/homes/{other}/hubs/claim', {'claim_code': second['claim_code']})
    assert house.put({'devices': [device(5)]}, token=second['hub_token']).status_code == 200
    assert call('owner', 'POST', f'/v1/homes/{house.home}/hubs/{house.hub["hub_id"]}/revoke', {}).status_code == 200
    assert rows(house.db, 'SELECT COUNT(*) FROM hub_devices WHERE hub_id=?', house.hub['hub_id']) == [(0,)]
    assert rows(house.db, 'SELECT COUNT(*) FROM hub_inventory WHERE hub_id=?', house.hub['hub_id']) == [(0,)]
    assert house.put({'devices': [device()]}).status_code == 401
    assert house.listing().json == {'devices': [], 'updated_at': None, 'hub_online': False}
    assert call('outsider', 'DELETE', f'/v1/homes/{other}', {'confirmation_name': 'B'}).status_code == 200
    assert rows(house.db, 'SELECT COUNT(*) FROM hub_devices') == [(0,)]
    assert rows(house.db, 'SELECT COUNT(*) FROM hub_inventory') == [(0,)]
    assert rows(house.db, 'PRAGMA foreign_key_check') == []


def test_hub_online_follows_the_control_heartbeat_rule(setup):
    db, now, homes, push, owner, member, outsider, home, other, ids, hub = setup
    inventory, control = Inventory(db, clock=lambda: now[0]), Controls(db, clock=lambda: now[0])
    stored = validate([device(reported_at=now[0])], now[0])
    assert inventory.replace(hub['hub_token'], stored) == {'status': 'stored', 'count': 1}
    listed = inventory.devices(home, member)
    assert listed['hub_online'] is False and listed['updated_at'] == now[0]
    control.heartbeat(hub['hub_token'], [])
    assert inventory.devices(home, member)['hub_online'] is True
    assert control.status(home, member)['online'] is True
    now[0] += Controls.ONLINE_SECONDS
    assert inventory.devices(home, member)['hub_online'] is control.status(home, member)['online'] is False
    with pytest.raises(APIError) as caught:
        inventory.devices(home, outsider)
    assert caught.value.status == 404
    with pytest.raises(APIError) as caught:
        inventory.replace('hub_' + 'x' * 43, stored)
    assert caught.value.code == 'invalid_hub_credentials'
    with pytest.raises(APIError):  # the future bound uses the server clock
        validate([device(reported_at=now[0] + 301)], now[0])
    assert validate([device(reported_at=now[0] + 300)], now[0])[0]['reported_at'] == now[0] + 300
