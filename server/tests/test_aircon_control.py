"""House isolation, current authority, expiry and at-most-once physical execution."""

import importlib.util
import json
import logging
import sqlite3
import sys
import urllib.error
import uuid
from pathlib import Path

import pytest

from tests.test_central_push import setup as setup
import central_server.control as control_module
from central_server.control import ALLOWED_ACTIONS, Controls
from central_server.households import APIError, Identity
from central_server.web import create_app
from central_server.storage import initialize

spec = importlib.util.spec_from_file_location('control_agent', Path(__file__).parents[1]/'services/pi-central-agent/agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)
DEVICE = 'a'*32


def test_schema_four_upgrade_preserves_runtime_household_hub_and_notification_settings(setup):
    db, _, _, _, _, _, _, _, _, _, _ = setup
    with sqlite3.connect(db) as conn:
        before={table:conn.execute('SELECT * FROM '+table).fetchall() for table in
                ('runtime_metadata','users','homes','memberships','hubs','installations','notification_preferences')}
        for table in ('control_commands','control_devices','control_hubs','server_identity',
                      'hub_inventory','hub_devices','notification_levels','quiet_hours'):
            conn.execute('DROP TABLE '+table)
        conn.execute('PRAGMA user_version=4')
    initialize(db); initialize(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone() == (8,)
        for table,rows in before.items():
            assert conn.execute('SELECT * FROM '+table).fetchall() == rows
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)


@pytest.fixture
def system(setup):
    db, now, homes, _, owner, viewer, outsider, home, other, _, hub = setup
    control = Controls(db, clock=lambda: now[0])
    control.heartbeat(hub['hub_token'], [{'id': DEVICE, 'name': 'Test air conditioner'}])
    return control, now, homes, owner, viewer, outsider, home, other, hub


def issue(system, *, user=None, request=None, action='power_off'):
    c, _, _, owner, _, _, home, _, _ = system
    return c.enqueue(home, user or owner, request or str(uuid.uuid4()), DEVICE, action)


def test_viewer_outsider_and_offline_hub_cannot_control(system):
    c, now, _, owner, viewer, outsider, home, _, _ = system
    assert c.status(home, viewer)['can_control'] is False
    for user, status in [(viewer, 403), (outsider, 404)]:
        with pytest.raises(APIError) as e: issue(system, user=user)
        assert e.value.status == status
    now[0] += 26
    assert c.status(home, owner)['online'] is False
    with pytest.raises(APIError) as e: issue(system)
    assert e.value.code == 'control_offline'


def test_duplicate_request_single_delivery_and_other_house_hub_isolation(system):
    c, _, homes, owner, _, outsider, home, other, hub = system
    command = issue(system)
    assert issue(system, request=command['id'])['id'] == command['id']
    other_hub = homes.provision_hub(); homes.claim(other, outsider, other_hub['claim_code'])
    assert c.next(other_hub['hub_token'])['command'] is None
    with pytest.raises(APIError): c.command(other, outsider, command['id'])
    delivered = c.next(hub['hub_token'])['command']
    assert delivered['id'] == command['id']
    assert c.next(hub['hub_token'])['command'] is None
    with pytest.raises(APIError): c.result(other_hub['hub_token'], command['id'], delivered['attempt_token'], 'sent')
    with pytest.raises(APIError): c.result(hub['hub_token'], command['id'], 'f'*64, 'sent')
    c.result(hub['hub_token'], command['id'], delivered['attempt_token'], 'sent')
    c.result(hub['hub_token'], command['id'], delivered['attempt_token'], 'sent')
    assert c.command(home, owner, command['id'])['state'] == 'sent'
    assert 'attempt_token' not in c.command(home, owner, command['id'])


@pytest.mark.parametrize('change', ['revoke', 'viewer', 'disabled', 'unlinked'])
def test_queued_command_rechecks_authority_and_device_before_delivery(system, change):
    c, _, homes, owner, viewer, _, home, _, hub = system
    homes.change_member(home, owner, viewer, role='member')
    command = issue(system, user=viewer)
    if change == 'revoke': homes.change_member(home, owner, viewer)
    elif change == 'viewer': homes.change_member(home, owner, viewer, role='viewer')
    elif change == 'disabled':
        with sqlite3.connect(c.database) as conn: conn.execute('UPDATE users SET active=0 WHERE id=?', (viewer,))
    else: c.heartbeat(hub['hub_token'], [])
    assert c.next(hub['hub_token'])['command'] is None
    assert c.command(home, owner, command['id'])['state'] == 'cancelled'


def test_expired_queued_command_never_delivers_but_lost_delivery_is_unknown(system):
    c, now, _, owner, _, _, home, _, hub = system
    first = issue(system)
    now[0] += 31
    assert c.next(hub['hub_token'])['command'] is None
    assert c.command(home, owner, first['id'])['state'] == 'expired'
    c.heartbeat(hub['hub_token'], [{'id': DEVICE, 'name': 'test'}])
    second = issue(system)
    c.next(hub['hub_token'])
    now[0] += 51
    assert c.command(home, owner, second['id'])['state'] == 'unknown'
    assert c.next(hub['hub_token'])['command'] is None


def test_busy_conflicting_reuse_revoked_hub_and_deleted_home(system):
    c, _, homes, owner, _, _, home, _, hub = system
    first = issue(system)
    with pytest.raises(APIError) as e: issue(system)
    assert e.value.code == 'control_busy'
    with pytest.raises(APIError) as e: issue(system, request=first['id'], action='cool_on')
    assert e.value.code == 'control_request_conflict'
    homes.delete_home(home, owner, 'one')
    with pytest.raises(APIError): c.next(hub['hub_token'])


def test_real_routes_validate_bodies_auth_and_full_agent_flow(system, tmp_path):
    c, _, _, owner, _, _, home, _, hub = system
    class Verifier:
        def verify(self, token):
            if token not in ('owner', 'member'): raise APIError('invalid_credentials', 401)
            return Identity('issuer', token, token+'@example.test')
    app = create_app(c.database, identity_verifier=Verifier()); app.extensions['control'].clock = c.clock
    client = app.test_client()
    path = '/v1/homes/'+home+'/control/commands'
    body = {'request_id':str(uuid.uuid4()), 'device_id':DEVICE, 'action':'cool_on'}
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={'Authorization':'Bearer member'}).status_code == 403
    auth = {'Authorization':'Bearer owner'}
    assert client.post(path, json={**body,'url':'https://example.test'}, headers=auth).status_code == 400
    assert client.post(path, json={**body,'action':'toggle'}, headers=auth).status_code == 400
    assert client.put('/v1/hub/control/status',json={'devices':[]},headers=auth).status_code == 401
    assert client.post(path, json=body, headers=auth).status_code == 202
    calls = []
    class Controller:
        def devices(self): return [{'id': DEVICE, 'name':'test'}]
        def execute(self, command): calls.append(command['action']); return 'sent'
    class Channel:
        def request(self, path, body, method='POST'):
            response=client.open(path,method=method,json=body,headers={'Authorization':'Bearer '+hub['hub_token']})
            assert response.status_code == 200, response.json
            return response.json
    state=agent.Store(tmp_path/'outbox.sqlite3')
    agent.poll_control(state, Channel(), Controller())
    agent.poll_control(state, Channel(), Controller())
    assert calls == ['cool_on']
    assert c.command(home, owner, body['request_id'])['state'] == 'sent'


@pytest.mark.parametrize('action', ['power_off', 'swing_toggle', 'led_toggle'])
def test_pi_crash_before_result_never_resends_physical_command(tmp_path, action):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':action,'attempt_token':'b'*64,'remaining_seconds':30}
    state=agent.Store(tmp_path/'outbox.sqlite3')
    assert state.begin_control(command)
    resumed=agent.Store(state.path)
    assert not resumed.begin_control(command)
    assert resumed.pending_result()['state'] == 'unknown'


def test_lost_result_only_retries_result_and_slow_delivery_expires_without_ir(tmp_path):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':'power_off','attempt_token':'b'*64,'remaining_seconds':30}
    calls=[]
    class Controller:
        def devices(self): return [{'id': DEVICE, 'name': 'test'}]
        def execute(self, command): calls.append('IR');return 'sent'
    class Channel:
        failed=False
        def request(self,path,body,method='POST'):
            if path.endswith('/next'): return {'command':command}
            if path.endswith('/result') and not self.failed:
                self.failed=True; raise OSError('lost result')
            return {}
    state=agent.Store(tmp_path/'first.sqlite3');channel=Channel()
    with pytest.raises(OSError): agent.poll_control(state,channel,Controller())
    agent.poll_control(state,channel,Controller())
    assert calls == ['IR']
    state=agent.Store(tmp_path/'second.sqlite3');times=iter([0,31]);channel.failed=True
    agent.poll_control(state,channel,Controller(),monotonic=lambda:next(times))
    assert calls == ['IR']


@pytest.mark.parametrize('origin',['https://example.test','http://example.test:8001','http://192.168.1.2:8001','http://127.0.0.1:8001/secret','http://user@127.0.0.1:8001'])
def test_controller_origin_cannot_be_an_external_or_arbitrary_url(origin):
    with pytest.raises(ValueError): agent.LocalController(origin)


def test_only_allowlisted_payloads_and_real_transmission_report_sent():
    controller=agent.LocalController('http://127.0.0.1:8001')
    calls=[]
    controller.request=lambda path,value,timeout=None: (calls.append(value) or {'transmission':{'status':'sent'}})
    assert controller.execute({'device_id':DEVICE,'action':'cool_on'}) == 'sent'
    assert calls[-1] == {'action':'set_state','power':True,'mode':'cool','temperature_c':24,'fan':'auto'}
    assert controller.execute({'device_id':DEVICE,'action':'power_off'}) == 'sent'
    assert calls[-1] == {'action':'set_state','power':False}
    assert controller.execute({'device_id':DEVICE,'action':'toggle'}) == 'failed'
    controller.request=lambda path,value,timeout=None: {'transmission':{'status':'mock_recorded'}}
    assert controller.execute({'device_id':DEVICE,'action':'power_off'}) == 'unknown'


@pytest.mark.parametrize('action', sorted(ALLOWED_ACTIONS))
def test_every_profile_command_passes_queue_and_existing_pi_resolver_once(system, tmp_path, action):
    # Use the real existing Pi command resolver and profile, never a hardware transport.
    sys.path.insert(0, str(Path(__file__).parents[2]))
    from app.devices.catalog import DeviceProfileCatalog
    from app.devices.commands import DeviceCommandResolver
    resolver=DeviceCommandResolver(DeviceProfileCatalog(Path(__file__).parents[2]/'device_profiles'))
    c, _, _, owner, _, _, home, _, hub=system
    assert ALLOWED_ACTIONS == frozenset(agent.CONTROL_PAYLOADS)
    command=issue(system,action=action)
    calls=[]
    controller=agent.LocalController('http://127.0.0.1:8001')
    controller.devices=lambda:[{'id':DEVICE,'name':'test'}]
    def execute(path,payload,timeout=None):
        assert path == '/api/v1/devices/'+DEVICE+'/commands'
        # economy is refused (422) by the Pi app unless the AC is known to be cooling.
        resolved=resolver.resolve('air_conditioner/Carrier/CS-A061GS',payload,{'power':True,'mode':'cool','temperature_c':24,'fan':'auto'})
        assert resolved['command_id'] == ('cool_24_auto' if action=='cool_on' else action)
        calls.append(resolved['frames_hex'])
        return {'transmission':{'status':'sent'}}
    controller.request=execute
    class Channel:
        def request(self,path,body,method='POST'):
            if path.endswith('/status'):return c.heartbeat(hub['hub_token'],body['devices'])
            if path.endswith('/next'):return c.next(hub['hub_token'])
            return c.result(hub['hub_token'],command['id'],body['attempt_token'],body['state'])
    store=agent.Store(tmp_path/'outbox.sqlite3')
    agent.poll_control(store,Channel(),controller)
    agent.poll_control(store,Channel(),controller)
    assert len(calls)==1
    assert c.command(home,owner,command['id'])['state']=='sent'


@pytest.mark.parametrize('action', [None,[],{},'cool_16_auto','cool_31_auto','cool_24_turbo',
                                  'cool_017_auto','cool_24_auto/../../','heat','POWER_TOGGLE'])
def test_control_api_rejects_unreviewed_actions_and_parameters(system, action):
    c, _, _, _, _, _, home, _, _=system
    class Verifier:
        def verify(self, token):return Identity('issuer','owner','owner@example.test')
    client=create_app(c.database,identity_verifier=Verifier()).test_client()
    response=client.post('/v1/homes/'+home+'/control/commands',
                         headers={'Authorization':'Bearer owner'},
                         json={'request_id':str(uuid.uuid4()),'device_id':DEVICE,'action':action})
    assert response.status_code==400
    with sqlite3.connect(c.database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM control_commands').fetchone()==(0,)


class RouteChannel:
    """Real hub routes; a non-200 reply raises HTTPError as ControlChannel does."""
    def __init__(self, c, token):
        app = create_app(c.database); app.extensions['control'].clock = c.clock
        self.client, self.token = app.test_client(), token
    def request(self, path, body, method='POST'):
        response = self.client.open(path, method=method, json=body, headers={'Authorization':'Bearer '+self.token})
        if response.status_code != 200:
            raise urllib.error.HTTPError(path, response.status_code, 'fixture', {}, None)
        return response.json


class Recorder:
    def __init__(self): self.calls = []
    def devices(self): return [{'id': DEVICE, 'name': 'test'}]
    def execute(self, command): self.calls.append(command['action']); return 'sent'


def dispatching(command, results):
    class Channel:
        def request(self, path, body, method='POST'):
            if path.endswith('/next'): return {'command': command}
            if path.endswith('/result'): results.append(body['state'])
            return {}
    return Channel()


def test_unsupported_action_from_newer_server_reports_failed_without_ir(system, tmp_path, monkeypatch):
    c, now, _, owner, _, _, home, _, hub = system
    monkeypatch.setattr(control_module, 'ALLOWED_ACTIONS', ALLOWED_ACTIONS | {'heat_24_auto'})
    command = issue(system, action='heat_24_auto')
    controller, store = Recorder(), agent.Store(tmp_path/'outbox.sqlite3')
    agent.poll_control(store, RouteChannel(c, hub['hub_token']), controller)
    assert controller.calls == [] and store.pending_result() is None
    assert c.command(home, owner, command['id'])['state'] == 'failed'
    now[0] += 4
    assert issue(system)['state'] == 'queued'


@pytest.mark.parametrize('remaining,state', [(0,'expired'), (-1,'expired'), (45,'failed'), ('30','failed'), (float('nan'),'failed'), (None,'failed')])
def test_invalid_command_window_reports_without_ir(tmp_path, remaining, state):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':'power_off','attempt_token':'b'*64,'remaining_seconds':remaining}
    results, controller = [], Recorder()
    agent.poll_control(agent.Store(tmp_path/'outbox.sqlite3'), dispatching(command, results), controller)
    assert controller.calls == [] and results == [state]


def test_dispatch_for_unadvertised_device_reports_failed_without_ir(tmp_path):
    command={'id':str(uuid.uuid4()),'device_id':'c'*32,'action':'power_off','attempt_token':'b'*64,'remaining_seconds':30}
    results, controller, store = [], Recorder(), agent.Store(tmp_path/'outbox.sqlite3')
    agent.poll_control(store, dispatching(command, results), controller)
    assert controller.calls == [] and results == ['failed'] and store.pending_result() is None


class Exploding(Recorder):
    def execute(self, command): self.calls.append(command['action']); raise RuntimeError('lost after send')


@pytest.mark.parametrize('case,state', [('huge_window','failed'), ('device_without_id','failed'), ('execute_error','unknown')])
def test_errors_after_receipt_still_finish_and_never_resend(tmp_path, case, state):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':'power_off','attempt_token':'b'*64,
             'remaining_seconds':10**400 if case=='huge_window' else 30}
    controller = Exploding() if case=='execute_error' else Recorder()
    if case == 'device_without_id': controller.devices = lambda: [{'name': 'test'}]
    results, store = [], agent.Store(tmp_path/'outbox.sqlite3')
    channel = dispatching(command, results)
    agent.poll_control(store, channel, controller)
    agent.poll_control(store, channel, controller)  # redelivery of the same command
    assert results == [state] and store.pending_result() is None
    assert controller.calls == (['power_off'] if case=='execute_error' else [])
    with store.connect() as conn:
        assert [row[0] for row in conn.execute('SELECT state FROM control_receipts')] == [state]


@pytest.mark.parametrize('heartbeat_error', [None, OSError('down'), ValueError('bad json')])
def test_deferred_result_after_send_still_refreshes_heartbeat(tmp_path, heartbeat_error):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':'power_off','attempt_token':'b'*64,'remaining_seconds':30}
    paths = []
    class Channel:
        def request(self, path, body, method='POST'):
            paths.append(path.rsplit('/', 1)[-1])
            if path.endswith('/next'): return {'command': command}
            if path.endswith('/result'): raise urllib.error.HTTPError(path, 500, 'fixture', {}, None)
            if heartbeat_error and len(paths) > 1: raise heartbeat_error
            return {}
    controller, store = Recorder(), agent.Store(tmp_path/'outbox.sqlite3')
    with pytest.raises(urllib.error.HTTPError) as error:
        agent.poll_control(store, Channel(), controller)
    assert error.value.code == 500  # a failing refresh never hides the result error
    assert paths == ['status', 'next', 'result', 'status']
    assert controller.calls == ['power_off'] and store.pending_result()['state'] == 'sent'


def test_rejected_credential_on_result_sends_nothing_more(tmp_path):
    command={'id':str(uuid.uuid4()),'device_id':DEVICE,'action':'power_off','attempt_token':'b'*64,'remaining_seconds':30}
    sender = agent.Sender({'endpoint':'https://example.test','hub_token':'fixture-hub'})
    urls = []
    class Opener:
        def open(self, request, **kwargs):
            urls.append(request.full_url.rsplit('/', 1)[-1])
            if urls[-1] == 'result': raise urllib.error.HTTPError(request.full_url, 401, 'fixture', {}, None)
            return Reply({'command': command} if urls[-1] == 'next' else {'status': 'ready'})
    sender.opener = Opener()
    with pytest.raises(urllib.error.HTTPError):
        agent.poll_control(agent.Store(tmp_path/'outbox.sqlite3'), agent.ControlChannel({'endpoint':'https://example.test'}, sender), Recorder())
    assert sender.blocked and urls == ['status', 'next', 'result']


def test_repeatedly_deferred_result_is_logged_once(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(agent, 'LOGGED', {})
    store = agent.Store(tmp_path/'outbox.sqlite3')
    receipt = {'id': str(uuid.uuid4()), 'attempt_token': 'b'*64}
    store.begin_control(receipt); store.finish_control(receipt, 'sent')
    class Channel:
        def request(self, path, body, method='POST'):
            if path.endswith('/result'): raise urllib.error.HTTPError(path, 503, 'fixture', {}, None)
            return {'command': None}
    caplog.set_level(logging.WARNING)
    for _ in range(3):
        agent.poll_control(store, Channel(), Recorder())
    assert [r.getMessage() for r in caplog.records] == ['AIRCON_CONTROL_RESULT_DEFERRED status=503']
    assert store.pending_result() is not None


def test_rejected_pending_result_does_not_block_heartbeat(system, tmp_path):
    c, now, _, owner, _, _, home, _, hub = system
    store = agent.Store(tmp_path/'outbox.sqlite3', clock=c.clock)
    ghost = {'id': str(uuid.uuid4()), 'attempt_token': 'b'*64}
    store.begin_control(ghost); store.finish_control(ghost, 'sent')
    now[0] += 20
    command = issue(system)
    now[0] += 6
    assert c.status(home, owner)['online'] is False
    controller = Recorder()
    agent.poll_control(store, RouteChannel(c, hub['hub_token']), controller)
    assert c.status(home, owner)['online'] is True
    assert controller.calls == ['power_off'] and c.command(home, owner, command['id'])['state'] == 'sent'
    with store.connect() as conn:
        assert conn.execute('SELECT reported FROM control_receipts WHERE id=?', (ghost['id'],)).fetchone()[0] == 1


def test_unmatched_pending_result_after_relink_is_dropped_and_heartbeat_continues(system, tmp_path):
    c, now, homes, owner, _, _, home, _, hub = system
    issue(system)
    store = agent.Store(tmp_path/'outbox.sqlite3', clock=c.clock)
    assert store.begin_control(c.next(hub['hub_token'])['command'])
    store = agent.Store(store.path, clock=c.clock)  # crashed mid-send: receipt is now 'unknown'
    homes.revoke_hub(home, owner, hub['hub_id'])
    relinked = homes.provision_hub(); homes.claim(home, owner, relinked['claim_code'])
    agent.poll_control(store, RouteChannel(c, relinked['hub_token']), Recorder())
    assert c.status(home, owner)['online'] is True and store.pending_result() is None


@pytest.mark.parametrize('error,reported', [(400,True), (404,True), (409,True), (429,False), (500,False),
                                            (503,False), (OSError('lost'),False), (ValueError('bad json'),False)])
def test_pending_result_failure_never_blocks_heartbeat_and_next(tmp_path, error, reported):
    store = agent.Store(tmp_path/'outbox.sqlite3')
    receipt = {'id': str(uuid.uuid4()), 'attempt_token': 'b'*64}
    store.begin_control(receipt); store.finish_control(receipt, 'unknown')
    paths = []
    class Channel:
        def request(self, path, body, method='POST'):
            paths.append(path)
            if path.endswith('/result'):
                raise urllib.error.HTTPError(path, error, 'fixture', {}, None) if isinstance(error, int) else error
            return {'command': None}
    agent.poll_control(store, Channel(), Recorder())
    assert paths[1:] == ['/v1/hub/control/status', '/v1/hub/control/next']
    assert (store.pending_result() is None) is reported


@pytest.mark.parametrize('code', [401, 403])
def test_rejected_hub_credential_on_pending_result_still_stops(tmp_path, code):
    store = agent.Store(tmp_path/'outbox.sqlite3')
    receipt = {'id': str(uuid.uuid4()), 'attempt_token': 'b'*64}
    store.begin_control(receipt); store.finish_control(receipt, 'sent')
    sender = agent.Sender({'endpoint':'https://example.test','hub_token':'fixture-hub'})
    urls = []
    class Opener:
        def open(self, request, **kwargs):
            urls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, code, 'fixture', {}, None)
    sender.opener = Opener()
    with pytest.raises(urllib.error.HTTPError):
        agent.poll_control(store, agent.ControlChannel({'endpoint':'https://example.test'}, sender), Recorder())
    assert sender.blocked and len(urls) == 1 and store.pending_result() is not None


class Reply:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return json.dumps(self.body).encode()


def test_local_command_timeout_exceeds_pi_h2_wait():
    controller=agent.LocalController('http://127.0.0.1:8001')
    timeouts={}
    class Opener:
        def open(self, request, timeout):
            timeouts[request.full_url.rsplit('/', 1)[-1]] = timeout
            return Reply({'items': []} if request.data is None else {'transmission': {'status': 'sent'}})
    controller.opener=Opener()
    assert controller.devices() == []
    assert controller.execute({'device_id':DEVICE,'action':'power_off'}) == 'sent'
    # The Pi app waits 18 s for the H2 result; the server marks the hub offline after 25 s.
    assert timeouts['devices'] <= 15 and 18 < timeouts['commands'] < 25


@pytest.mark.parametrize('error,state', [(400,'failed'), (404,'failed'), (409,'failed'), (422,'failed'), (503,'failed'),
                                         (500,'unknown'), (502,'unknown'), (TimeoutError('timed out'),'unknown'),
                                         (urllib.error.URLError('reset'),'unknown')])
def test_local_refusal_is_failed_and_possible_send_is_unknown_without_retry(error, state):
    controller=agent.LocalController('http://127.0.0.1:8001')
    calls=[]
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, error, 'fixture', {}, None) if isinstance(error, int) else error
    controller.opener=Opener()
    # e.g. the Pi app answers 422 for economy while the AC is not cooling: no IR was sent.
    assert controller.execute({'device_id':DEVICE,'action':'economy'}) == state
    assert len(calls) == 1


@pytest.mark.parametrize('name,expected', [('\x01 \x01','Air conditioner'), ('\x01\u3000\x01','Air conditioner'),
                                           (' '*100+'x','x'), (None,'Air conditioner'), ('x'*79+' '+'y'*5,'x'*79),
                                           ('Living\x00 room','Living room'),
                                           # Cc above 0x1f (DEL) and Cf (bidi override, zero-width, BOM)
                                           ('Living\x7f room','Living room'), ('\u202eLiving\u200b room\ufeff','Living room'),
                                           ('\u200b\u202e\u2066','Air conditioner')])
def test_control_name_normalisation_matches_server(system, name, expected):
    c, _, _, owner, _, _, home, _, hub = system
    controller=agent.LocalController('http://127.0.0.1:8001')
    controller.request=lambda path, value=None, timeout=15: {'items': [{'id': DEVICE, 'name': name,
        'profile_id': 'air_conditioner/Carrier/CS-A061GS', 'zigbee_binding': {'type': 'h2_ir'}}]}
    devices=controller.devices()
    assert devices == [{'id': DEVICE, 'name': expected}]
    RouteChannel(c, hub['hub_token']).request('/v1/hub/control/status', {'devices': devices}, 'PUT')
    assert c.status(home, owner)['devices'] == [{'id': DEVICE, 'name': expected}]


def test_control_readiness_probe_follows_the_current_schema_version(system, setup, tmp_path, monkeypatch, capsys):
    """verify_control.py's A50 probe must not pin a schema number; it reads SCHEMA_VERSION."""
    import ast, shutil, time, urllib.request
    from central_server.storage import SCHEMA_VERSION
    db = setup[0]
    c, now, _, _, _, _, _, _, hub = system
    now[0] = time.time()
    c.heartbeat(hub['hub_token'], [{'id': DEVICE, 'name': 'Test air conditioner'}])  # live within 25 s
    tree = ast.parse((Path(__file__).parents[1]/'scripts/pi/verify_control.py').read_text(encoding='utf-8'))
    probe = next(ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'PHONE')
    assert '(5,)' not in probe and 'SCHEMA_VERSION' in probe
    home = tmp_path/'home'
    for relative in ('.local/share/aircon-central', '.local/state/aircon-public-tunnel'):
        (home/relative).mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    shutil.copy(db, home/'.local/share/aircon-central/central.sqlite3')
    with sqlite3.connect(home/'.local/share/aircon-central/central.sqlite3') as conn:
        conn.execute('PRAGMA journal_mode=DELETE')
    # The probe prefers the fixed-domain tunnel state and needs a connected tunnel with a URL.
    (home/'.local/state/aircon-public-tunnel/endpoint.json').write_text(
        json.dumps({'url': 'https://example.test', 'status': 'connected'}))
    monkeypatch.setenv('HOME', str(home)); monkeypatch.setenv('USERPROFILE', str(home))
    monkeypatch.setattr(sys, 'path', list(sys.path))
    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, 'fixture', {}, None)
    monkeypatch.setattr(urllib.request, 'urlopen', refuse)
    exec(probe, {})
    out = capsys.readouterr().out
    assert 'DATABASE=ok SCHEMA='+str(SCHEMA_VERSION) in out and out.count('REJECTED_AUTH=401') == 3
    assert out.strip().endswith('CONTROL_READINESS=PASS NO_PHYSICAL_COMMAND_SENT=TRUE')
