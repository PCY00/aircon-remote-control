"""Signed test identities exercise the real verifier and current household authority."""
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).parents[1]/'services/central-server'))
from central_server.auth import FirebaseIdentity
from central_server.households import APIError
from central_server.storage import initialize
from central_server.web import create_app


@pytest.fixture
def environment(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    class Keys:
        def get(self):
            return {'fixture': private.public_key()}
    db = tmp_path/'central.sqlite3'
    initialize(db)
    verifier = FirebaseIdentity('test-project', certificates=Keys())
    app = create_app(db, identity_verifier=verifier)
    def token(person, **changes):
        now = int(time.time())
        claims = dict(sub=person, email=person+'@example.test', email_verified=True,
                      firebase={'sign_in_provider':'google.com'}, auth_time=now,
                      iat=now, exp=now+3600, aud='test-project',
                      iss='https://securetoken.google.com/test-project')
        claims.update(changes)
        return jwt.encode(claims, private, algorithm='RS256', headers={'kid':'fixture'})
    def call(person, method, path, value=None, **changes):
        return app.test_client().open(path, method=method, json=value,
            headers={'Authorization':'Bearer '+token(person, **changes)})
    return db, app, verifier, token, call


@pytest.mark.parametrize('changes', [dict(aud='other-project'), dict(iss='other'), dict(exp=1),
    dict(auth_time=2**40), dict(iat=2**40), dict(sub=''), dict(email_verified=False),
    dict(firebase={'sign_in_provider':'password'}), dict(exp=True), dict(aud=['test-project','other'])])
def test_invalid_identity_rejected(environment, changes):
    _, _, verifier, token, _ = environment
    with pytest.raises(APIError) as caught:
        verifier.verify(token('owner', **changes))
    assert caught.value.status == 401


def test_unsigned_wrong_key_and_tampered_token_rejected(environment):
    _, _, verifier, token, _ = environment
    valid = token('owner')
    payload = jwt.decode(valid, options={'verify_signature':False})
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid = [jwt.encode(payload, '', algorithm='none', headers={'kid':'fixture'}),
               jwt.encode(payload, 'x'*32, algorithm='HS256', headers={'kid':'fixture'}),
               jwt.encode(payload, other, algorithm='RS256', headers={'kid':'fixture'}),
               valid.rsplit('.',1)[0]+'.AAAA', 'malformed']
    for value in invalid:
        with pytest.raises(APIError) as caught:
            verifier.verify(value)
        assert caught.value.status == 401


def test_family_isolation_revoke_and_hub_authority(environment):
    db, app, _, _, call = environment
    service = app.extensions['households']
    a = call('a','POST','/v1/homes',{'name':'A'}).json['id']
    b = call('b','POST','/v1/homes',{'name':'B'}).json['id']
    owner = call('a','GET','/v1/me').json['user_id']
    outsider = call('b','GET','/v1/me').json['user_id']
    for suffix in ('','/members','/hubs','/events'):
        assert call('b','GET','/v1/homes/'+a+suffix).status_code == 404
    invitation = call('a','POST',f'/v1/homes/{a}/invitations',
                       {'email':'family@example.test','role':'viewer'}).json['invitation_token']
    assert call('b','POST','/v1/invitations/accept',{'invitation_token':invitation}).status_code == 404
    assert call('family','POST','/v1/invitations/accept',{'invitation_token':invitation}).status_code == 200
    assert call('family','POST','/v1/invitations/accept',{'invitation_token':invitation}).status_code == 404
    member = call('family','GET','/v1/me').json['user_id']
    assert call('family','GET',f'/v1/homes/{a}').status_code == 200
    assert call('family','GET',f'/v1/homes/{a}/members').status_code == 403
    assert call('family','PATCH',f'/v1/homes/{a}/members/{member}',{'role':'member'}).status_code == 403
    assert call('a','PATCH',f'/v1/homes/{a}/members/{member}',{'role':'owner'}).status_code == 400
    assert call('a','POST',f'/v1/homes/{a}/members/{owner}/revoke',{}).status_code == 409
    assert call('a','POST',f'/v1/homes/{a}/members/{outsider}/revoke',{}).status_code == 404
    hub = service.provision_hub()
    assert call('family','POST',f'/v1/homes/{a}/hubs/claim',{'claim_code':hub['claim_code']}).status_code == 403
    assert call('a','POST',f'/v1/homes/{a}/hubs/claim',{'claim_code':hub['claim_code']}).status_code == 200
    assert call('b','POST',f'/v1/homes/{b}/hubs/claim',{'claim_code':hub['claim_code']}).status_code == 404
    event = {'event_id':'evt1','kind':'sensor.open','payload':{'home_id':b}}
    def ingest(value):
        return app.test_client().post('/v1/hub/events',json=value,
                  headers={'Authorization':'Bearer '+hub['hub_token']})
    assert ingest(event|{'home_id':b}).status_code == 400
    first = ingest(event)
    assert first.status_code == 200 and not first.json['duplicate']
    assert ingest(event).json['duplicate']
    assert ingest(event|{'kind':'sensor.closed'}).status_code == 409
    eid = first.json['id']
    assert call('a','GET',f'/v1/homes/{a}/events/{eid}').status_code == 200
    assert call('b','GET',f'/v1/homes/{b}/events/{eid}').status_code == 404
    assert call('b','GET',f'/v1/homes/{b}/events').json['events'] == []
    assert call('a','POST',f'/v1/homes/{a}/members/{member}/revoke',{}).status_code == 200
    assert call('family','GET',f'/v1/homes/{a}/events').status_code == 404
    assert call('a','POST',f'/v1/homes/{a}/hubs/{hub["hub_id"]}/revoke',{}).status_code == 200
    assert ingest(event).status_code == 401
    raw = db.read_bytes()
    assert hub['hub_token'].encode() not in raw and invitation.encode() not in raw


def test_invitation_expiry_race_and_rejoin(environment):
    _, app, _, _, call = environment
    service = app.extensions['households']
    home = call('a','POST','/v1/homes',{'name':'A'}).json['id']
    def invite():
        return call('a','POST',f'/v1/homes/{home}/invitations',
                    {'email':'family@example.test','role':'member'}).json['invitation_token']
    unused, chosen = invite(), invite()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: call('family','POST','/v1/invitations/accept',
                                              {'invitation_token':chosen}).status_code, range(2)))
    assert sorted(results) == [200,404]
    member = call('family','GET','/v1/me').json['user_id']
    call('a','POST',f'/v1/homes/{home}/members/{member}/revoke',{})
    assert call('family','POST','/v1/invitations/accept',{'invitation_token':unused}).status_code == 404
    fresh = invite()
    assert call('family','POST','/v1/invitations/accept',{'invitation_token':fresh}).status_code == 200
    call('a','POST',f'/v1/homes/{home}/members/{member}/revoke',{})
    expired = invite()
    service.clock = lambda: time.time()+86401
    assert call('family','POST','/v1/invitations/accept',{'invitation_token':expired}).status_code == 404


def test_no_configuration_or_forged_identity_headers_are_closed(tmp_path):
    db = tmp_path/'central.sqlite3'; initialize(db)
    client = create_app(db).test_client()
    assert client.get('/v1/me',headers={'X-User-ID':'owner'}).status_code == 401
    assert client.get('/v1/me',headers={'Authorization':'Bearer anything'}).status_code == 503


def test_migration_preserves_metadata_and_rolls_back_invalid_change(tmp_path, monkeypatch):
    import central_server.storage as storage
    db = tmp_path/'central.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE runtime_metadata(id INTEGER PRIMARY KEY,installation_id TEXT,created_at TEXT)')
        conn.execute("INSERT INTO runtime_metadata VALUES(1,'keep-id','keep-date')")
        conn.execute('PRAGMA user_version=1')
    monkeypatch.setattr(storage,'STATEMENTS',('CREATE TABLE intermediate(id TEXT)', 'INVALID SQL'))
    with pytest.raises(sqlite3.Error): initialize(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 1
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='intermediate'").fetchone() is None
    monkeypatch.undo(); initialize(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT * FROM runtime_metadata').fetchone() == (1,'keep-id','keep-date')
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 2


def test_disabled_account_and_recreated_email_do_not_gain_old_rights(environment):
    db, _, _, _, call = environment
    home = call('a','POST','/v1/homes',{'name':'A'}).json['id']
    uid = call('a','GET','/v1/me').json['user_id']
    assert call('new-a','GET','/v1/me',email='a@example.test').status_code == 409
    with sqlite3.connect(db) as conn:
        conn.execute('UPDATE users SET active=0 WHERE id=?',(uid,))
    assert call('a','GET',f'/v1/homes/{home}').status_code == 403
    assert call('a','POST','/v1/homes',{'name':'another'}).status_code == 403


def test_hub_expiry_replacement_and_invalid_payload(environment):
    _, app, _, _, call = environment
    service = app.extensions['households']
    home = call('a','POST','/v1/homes',{'name':'A'}).json['id']
    expired = service.provision_hub(lifetime=-1)
    assert call('a','POST',f'/v1/homes/{home}/hubs/claim',{'claim_code':expired['claim_code']}).status_code == 404
    first, second = service.provision_hub(), service.provision_hub()
    for hub, status in ((first,200),(second,409)):
        assert call('a','POST',f'/v1/homes/{home}/hubs/claim',{'claim_code':hub['claim_code']}).status_code == status
    client = app.test_client()
    for payload in ({'bad':float('nan')}, {'big':'x'*2049}, []):
        assert client.post('/v1/hub/events',json={'event_id':'evt','kind':'sensor.open','payload':payload},
            headers={'Authorization':'Bearer '+first['hub_token']}).status_code == 400
    call('a','POST',f'/v1/homes/{home}/hubs/{first["hub_id"]}/revoke',{})
    assert call('a','POST',f'/v1/homes/{home}/hubs/claim',{'claim_code':second['claim_code']}).status_code == 200


def test_public_certificate_cache_and_network_failure(monkeypatch):
    import central_server.auth as auth
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, UTC
    private = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'fixture')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key())
            .serial_number(1).not_valid_before(datetime.now(UTC)-timedelta(days=1))
            .not_valid_after(datetime.now(UTC)+timedelta(days=1)).sign(private,hashes.SHA256()))
    raw = json.dumps({'fixture':cert.public_bytes(serialization.Encoding.PEM).decode()}).encode()
    calls = []
    clock = [100.0]
    class Response:
        headers = {'Cache-Control':'public, max-age=100','Age':'10'}
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def geturl(self): return auth.CERTIFICATE_URL
        def read(self,limit): return raw
    def fetch(url,timeout): calls.append(url); return Response()
    monkeypatch.setattr(auth.urllib.request,'urlopen',fetch)
    monkeypatch.setattr(auth.time,'monotonic',lambda:clock[0])
    cache = auth.Certificates()
    assert 'fixture' in cache.get() and 'fixture' in cache.get() and len(calls) == 1
    clock[0] = 191.0
    def failure(*args,**kwargs): raise OSError('offline')
    monkeypatch.setattr(auth.urllib.request,'urlopen',failure)
    with pytest.raises(APIError) as caught: cache.get()
    assert caught.value.status == 503
    with pytest.raises(APIError): cache.get()
