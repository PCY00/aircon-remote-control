"""Per-install ES256 server key the family app pins; the signed Host binds the address it typed."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

STATEMENTS = (
    'CREATE TABLE server_identity (id INTEGER PRIMARY KEY CHECK(id=1), '
    'private_key_pem TEXT NOT NULL, created_at REAL NOT NULL)',
)
PREFIX = 'aircon-central-identity\n'


def ensure_key(connection, now=None) -> None:
    """Generate the key once; an existing key is never replaced because phones have pinned it."""
    if not connection.execute('SELECT 1 FROM server_identity WHERE id=1').fetchone():
        pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        connection.execute('INSERT INTO server_identity VALUES (1,?,?)',
                           (pem, time.time() if now is None else now))


def message(nonce: str, host: str, issued_at: int) -> bytes:
    return (PREFIX+nonce+'\n'+host+'\n'+str(issued_at)).encode()


class ServerIdentity:
    def __init__(self, database: Path, *, clock=time.time):
        self.database, self.clock, self.key = database, clock, None

    def private_key(self):
        if self.key is None:
            # Read-only URI: an identity request must never create an empty database.
            with closing(sqlite3.connect(self.database.resolve().as_uri()+'?mode=ro', uri=True, timeout=2)) as conn:
                row = conn.execute('SELECT private_key_pem FROM server_identity WHERE id=1').fetchone()
            if not row:
                raise sqlite3.OperationalError('server identity missing')
            self.key = serialization.load_pem_private_key(row[0].encode(), password=None)
        return self.key

    def public_der(self) -> bytes:
        return self.private_key().public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_der()).hexdigest()

    def describe(self, nonce: str, host: str) -> dict:
        issued_at = int(self.clock())
        signature = self.private_key().sign(message(nonce, host, issued_at), ec.ECDSA(hashes.SHA256()))
        return {'version': 1, 'algorithm': 'ES256',
                'public_key': base64.b64encode(self.public_der()).decode(),
                'fingerprint': self.fingerprint(), 'host': host, 'issued_at': issued_at,
                'signature': base64.b64encode(signature).decode()}
