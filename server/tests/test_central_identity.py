"""Per-install server key: stable across restarts, host-bound signature, strict nonce, schema 6."""

import base64
import hashlib
import secrets
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

sys.path.insert(0, str(Path(__file__).parents[1] / 'services/central-server'))
from central_server.identity import ServerIdentity, message
from central_server.storage import initialize, ready
from central_server.web import create_app


def pem(db):
    with sqlite3.connect(db) as conn:
        return conn.execute('SELECT private_key_pem FROM server_identity WHERE id=1').fetchone()[0]


def verify(reply, nonce):
    public = serialization.load_der_public_key(base64.b64decode(reply['public_key']))
    public.verify(base64.b64decode(reply['signature']),
                  message(nonce, reply['host'], reply['issued_at']), ec.ECDSA(hashes.SHA256()))
    return public


def test_key_is_generated_once_and_fingerprint_is_sha256_of_der_spki(tmp_path):
    db = tmp_path / 'central.sqlite3'
    initialize(db)
    first = pem(db)
    initialize(db)  # a restart must never rotate the key the phones pinned
    assert pem(db) == first and first.startswith('-----BEGIN PRIVATE KEY-----')
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM server_identity').fetchone() == (1,)
    private = serialization.load_pem_private_key(first.encode(), password=None)
    assert isinstance(private.curve, ec.SECP256R1)
    der = private.public_key().public_bytes(serialization.Encoding.DER,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    assert ServerIdentity(db).fingerprint() == hashlib.sha256(der).hexdigest()
    assert initialize(tmp_path / 'other.sqlite3') is None and pem(tmp_path / 'other.sqlite3') != first


def test_identity_route_signs_nonce_and_lowercased_host_without_authentication(tmp_path):
    db = tmp_path / 'central.sqlite3'
    initialize(db)
    client = create_app(db).test_client()  # no identity verifier: usable before any sign-in
    nonce = secrets.token_hex(16)
    before = int(time.time())
    response = client.get('/v1/server-identity?nonce=' + nonce, headers={'Host': 'Abc.TryCloudflare.com'})
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    reply = response.json
    assert set(reply) == {'version', 'algorithm', 'public_key', 'fingerprint', 'host', 'issued_at', 'signature'}
    assert reply['version'] == 1 and reply['algorithm'] == 'ES256' and reply['host'] == 'abc.trycloudflare.com'
    assert type(reply['issued_at']) is int and before <= reply['issued_at'] <= int(time.time())
    public = verify(reply, nonce)
    assert isinstance(public.curve, ec.SECP256R1)
    assert (reply['fingerprint'] == hashlib.sha256(base64.b64decode(reply['public_key'])).hexdigest()
            == ServerIdentity(db).fingerprint())
    with pytest.raises(InvalidSignature):
        verify(reply, secrets.token_hex(16))  # another nonce: replayed answers do not verify
    with pytest.raises(InvalidSignature):  # a relay cannot reuse the answer for its own host name
        public.verify(base64.b64decode(reply['signature']),
                      message(nonce, 'relay.example', reply['issued_at']), ec.ECDSA(hashes.SHA256()))
    ported = client.get('/v1/server-identity?nonce=' + nonce, headers={'Host': '127.0.0.1:8001'}).json
    assert ported['host'] == '127.0.0.1:8001' and ported['public_key'] == reply['public_key']
    verify(ported, nonce)


@pytest.mark.parametrize('query', ['', '?nonce=', '?nonce=' + 'a' * 31, '?nonce=' + 'a' * 33,
                                   '?nonce=' + 'A' * 32, '?nonce=' + 'g' * 32, '?nonce=' + 'a' * 32 + '%0a'])
def test_identity_route_rejects_malformed_nonce(tmp_path, query):
    db = tmp_path / 'central.sqlite3'
    initialize(db)
    response = create_app(db).test_client().get('/v1/server-identity' + query)
    assert response.status_code == 400 and response.json == {'error': 'invalid_body'}


def test_identity_route_is_rate_limited_and_unavailable_without_database(tmp_path):
    db = tmp_path / 'central.sqlite3'
    missing = create_app(db).test_client().get('/v1/server-identity?nonce=' + 'a' * 32)
    assert missing.status_code == 503 and missing.json == {'error': 'storage_unavailable'}
    assert not db.exists()
    initialize(db)
    app = create_app(db)
    clock = [0.0]
    app.extensions['limits']['identity'].clock = lambda: clock[0]
    client = app.test_client()
    path = '/v1/server-identity?nonce=' + 'a' * 32
    noisy = {'CF-Connecting-IP': '203.0.113.5'}
    assert all(client.get(path, headers=noisy).status_code == 200 for _ in range(60))
    limited = client.get(path, headers=noisy)
    assert limited.status_code == 429 and limited.json == {'error': 'rate_limited'}
    assert int(limited.headers['Retry-After']) >= 1
    # Another phone (other visitor address, or a direct loopback peer) is never locked out.
    assert client.get(path, headers={'CF-Connecting-IP': '198.51.100.7'}).status_code == 200
    assert client.get(path).status_code == 200  # keyed by the peer address without the tunnel header
    buckets = app.extensions['limits']['identity'].buckets
    assert {'203.0.113.5', '198.51.100.7'} < set(buckets) and len(buckets) == 3
    clock[0] += 1
    assert client.get(path, headers=noisy).status_code == 200


def test_schema_five_upgrade_keeps_data_and_adds_one_identity_key(tmp_path):
    db = tmp_path / 'central.sqlite3'
    initialize(db)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO users VALUES('u','i','s','e',1)")
        conn.execute("INSERT INTO homes VALUES('h','keep-home','u',1)")
        conn.execute("INSERT INTO memberships VALUES('h','u','owner',1,NULL)")
        conn.execute("INSERT INTO installations VALUES('phone','proof','u','private-token','binding',1,1000)")
        for table in ('server_identity', 'hub_inventory', 'hub_devices', 'notification_levels'):
            conn.execute('DROP TABLE '+table)  # a real schema-5 database has none of these
        conn.execute('PRAGMA user_version=5')
    initialize(db)
    initialize(db)
    with sqlite3.connect(db) as conn:
        assert conn.execute('PRAGMA user_version').fetchone() == (7,)
        assert conn.execute('SELECT name,active FROM homes').fetchall() == [('keep-home', 1)]
        assert conn.execute('SELECT token,binding FROM installations').fetchall() == [('private-token', 'binding')]
        assert conn.execute('SELECT COUNT(*) FROM server_identity').fetchone() == (1,)
        assert conn.execute('PRAGMA integrity_check').fetchone() == ('ok',)
    assert ready(db)


def test_admin_identity_prints_public_fingerprint_only(tmp_path, monkeypatch, capsys):
    from central_server import admin
    db = tmp_path / 'central.sqlite3'
    initialize(db)
    monkeypatch.setenv('A50_CENTRAL_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(sys, 'argv', ['admin', 'identity'])
    admin.main()
    out = capsys.readouterr().out
    fingerprint = ServerIdentity(db).fingerprint()
    assert 'SERVER_IDENTITY_FINGERPRINT=' + fingerprint in out
    assert ' '.join(fingerprint[i:i+4] for i in range(0, 64, 4)) in out
    assert 'PRIVATE KEY' not in out and pem(db).splitlines()[1] not in out
    monkeypatch.setattr(sys, 'argv', ['admin', 'provision-hub'])
    with pytest.raises(SystemExit):
        admin.main()  # credentials still require a private --output file
