"""Household authority is checked from current database state on every operation."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str
    email: str


class APIError(Exception):
    def __init__(self, code: str, status: int):
        self.code, self.status = code, status
        super().__init__(code)


def identifier() -> str:
    return str(uuid.uuid4())


def token_digest(kind: str, value: str) -> str:
    return hashlib.sha256((kind+'\0'+value).encode()).hexdigest()


class Households:
    def __init__(self, database: Path, *, clock=time.time):
        self.database, self.clock = database, clock

    @contextmanager
    def transaction(self, *, write=False):
        conn = sqlite3.connect(self.database, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def user(self, identity: Identity) -> str:
        with self.transaction(write=True) as conn:
            row = conn.execute('SELECT * FROM users WHERE issuer=? AND subject=?',
                               (identity.issuer, identity.subject)).fetchone()
            if row and not row['active']:
                raise APIError('account_disabled', 403)
            uid = row['id'] if row else identifier()
            try:
                if row:
                    if row['email'] != identity.email:
                        conn.execute('UPDATE users SET email=? WHERE id=?', (identity.email, uid))
                else:
                    conn.execute('INSERT INTO users(id,issuer,subject,email) VALUES (?,?,?,?)',
                                 (uid, identity.issuer, identity.subject, identity.email))
            except sqlite3.IntegrityError as error:
                raise APIError('identity_conflict', 409) from error
            return uid

    @staticmethod
    def access(conn, home: str, user: str, *, owner=False):
        row = conn.execute('SELECT m.role FROM memberships m JOIN users u ON u.id=m.user_id '
                           'WHERE m.home_id=? AND m.user_id=? AND m.active=1 AND u.active=1',
                           (home, user)).fetchone()
        if not row:
            raise APIError('not_found', 404)
        if owner and row['role'] != 'owner':
            raise APIError('owner_required', 403)
        return row['role']

    def audit(self, conn, home, user, kind):
        return conn.execute('INSERT INTO audit(home_id,actor_id,kind,created_at) VALUES (?,?,?,?)',
                            (home, user, kind, self.clock())).lastrowid

    def create_home(self, user: str, name: str):
        with self.transaction(write=True) as conn:
            if not conn.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user,)).fetchone():
                raise APIError('account_disabled', 403)
            home = identifier()
            conn.execute('INSERT INTO homes VALUES (?,?,?)', (home, name, user))
            conn.execute('INSERT INTO memberships(home_id,user_id,role) VALUES (?,?,?)',
                         (home, user, 'owner'))
            self.audit(conn, home, user, 'home_created')
            return {'id': home, 'name': name, 'role': 'owner'}

    def homes(self, user):
        with self.transaction() as conn:
            return [dict(row) for row in conn.execute(
                'SELECT h.id,h.name,m.role FROM homes h JOIN memberships m ON m.home_id=h.id '
                'JOIN users u ON u.id=m.user_id WHERE m.user_id=? AND m.active=1 AND u.active=1 ORDER BY h.id', (user,))]

    def home(self, home, user):
        with self.transaction() as conn:
            role = self.access(conn, home, user)
            row = conn.execute('SELECT id,name FROM homes WHERE id=?', (home,)).fetchone()
            return dict(row) | {'role': role}

    def members(self, home, user):
        with self.transaction() as conn:
            self.access(conn, home, user, owner=True)
            return [dict(row) for row in conn.execute(
                'SELECT u.id,u.email,m.role,m.active FROM memberships m JOIN users u ON u.id=m.user_id '
                'WHERE m.home_id=? ORDER BY u.id', (home,))]

    def invitation(self, home, user, email, role):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user, owner=True)
            target = conn.execute('SELECT id FROM users WHERE email=?', (email,)).fetchone()
            target_id = target['id'] if target else None
            if target_id and conn.execute('SELECT 1 FROM memberships WHERE home_id=? AND user_id=? '
                                          'AND active=1', (home, target_id)).fetchone():
                raise APIError('already_member', 409)
            token = 'invite_'+secrets.token_urlsafe(32)
            expires = self.clock()+86400
            sequence = self.audit(conn, home, user, 'invitation_created')
            conn.execute('INSERT INTO invitations(digest,home_id,email,target_id,role,created_seq,'
                         'expires_at) VALUES (?,?,?,?,?,?,?)',
                         (token_digest('invite', token), home, email, target_id, role, sequence, expires))
            return {'invitation_token': token, 'expires_at': expires, 'role': role}

    def accept(self, user, token):
        with self.transaction(write=True) as conn:
            invite = conn.execute('SELECT * FROM invitations WHERE digest=?',
                                  (token_digest('invite', token),)).fetchone()
            person = conn.execute('SELECT email FROM users WHERE id=? AND active=1',
                                  (user,)).fetchone()
            if (not invite or invite['consumed'] or invite['expires_at'] <= self.clock()
                    or not person or invite['email'] != person['email']
                    or (invite['target_id'] and invite['target_id'] != user)):
                raise APIError('invalid_invitation', 404)
            membership = conn.execute('SELECT * FROM memberships WHERE home_id=? AND user_id=?',
                                      (invite['home_id'], user)).fetchone()
            if membership and membership['active']:
                raise APIError('already_member', 409)
            if (membership and membership['revoked_seq'] is not None
                    and invite['created_seq'] <= membership['revoked_seq']):
                raise APIError('invalid_invitation', 404)
            conn.execute('INSERT INTO memberships(home_id,user_id,role,active) VALUES (?,?,?,1) '
                         'ON CONFLICT(home_id,user_id) DO UPDATE SET role=excluded.role,active=1',
                         (invite['home_id'], user, invite['role']))
            conn.execute('UPDATE invitations SET consumed=1 WHERE digest=?', (invite['digest'],))
            self.audit(conn, invite['home_id'], user, 'invitation_accepted')
            return {'home_id': invite['home_id'], 'role': invite['role']}

    def change_member(self, home, user, target, *, role=None):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user, owner=True)
            member = conn.execute('SELECT role,active FROM memberships WHERE home_id=? AND user_id=?',
                                  (home, target)).fetchone()
            if not member:
                raise APIError('not_found', 404)
            if member['role'] == 'owner':
                raise APIError('owner_protected', 409)
            if role:
                if not member['active']:
                    raise APIError('not_found', 404)
                conn.execute('UPDATE memberships SET role=? WHERE home_id=? AND user_id=?',
                             (role, home, target))
                self.audit(conn, home, user, 'member_role_changed')
            elif member['active']:
                sequence = self.audit(conn, home, user, 'member_revoked')
                conn.execute('UPDATE memberships SET active=0,revoked_seq=? '
                             'WHERE home_id=? AND user_id=?', (sequence, home, target))
            return {'status': 'updated'}

    def provision_hub(self, *, lifetime=600):
        with self.transaction(write=True) as conn:
            hub, credential = identifier(), 'hub_'+secrets.token_urlsafe(32)
            claim = 'claim_'+secrets.token_urlsafe(32)
            expires = self.clock()+lifetime
            conn.execute('INSERT INTO hubs(id,credential_digest,claim_digest,claim_expires_at) '
                         'VALUES (?,?,?,?)', (hub, token_digest('hub', credential),
                                             token_digest('claim', claim), expires))
            return {'hub_id': hub, 'hub_token': credential, 'claim_code': claim,
                    'claim_expires_at': expires}

    def claim(self, home, user, code):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user, owner=True)
            hub = conn.execute('SELECT * FROM hubs WHERE claim_digest=?',
                               (token_digest('claim', code),)).fetchone()
            if (not hub or not hub['active'] or hub['home_id'] is not None
                    or hub['claim_expires_at'] <= self.clock()):
                raise APIError('invalid_claim', 404)
            try:
                conn.execute('UPDATE hubs SET home_id=?,claim_digest=NULL WHERE id=?',
                             (home, hub['id']))
            except sqlite3.IntegrityError as error:
                raise APIError('home_hub_exists', 409) from error
            self.audit(conn, home, user, 'hub_claimed')
            return {'id': hub['id'], 'home_id': home}

    def hubs(self, home, user):
        with self.transaction() as conn:
            self.access(conn, home, user)
            return [dict(row) for row in conn.execute(
                'SELECT id,active FROM hubs WHERE home_id=? ORDER BY id', (home,))]

    def revoke_hub(self, home, user, hub):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user, owner=True)
            if not conn.execute('SELECT 1 FROM hubs WHERE id=? AND home_id=?', (hub, home)).fetchone():
                raise APIError('not_found', 404)
            conn.execute('UPDATE hubs SET active=0 WHERE id=? AND home_id=?', (hub, home))
            self.audit(conn, home, user, 'hub_revoked')
            return {'status': 'revoked'}

    def ingest(self, token, sender_id, kind, payload):
        with self.transaction(write=True) as conn:
            hub = conn.execute('SELECT id,home_id FROM hubs WHERE credential_digest=? AND active=1',
                               (token_digest('hub', token),)).fetchone()
            if not hub or hub['home_id'] is None:
                raise APIError('invalid_hub_credentials', 401)
            encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
            content = token_digest('event', kind+'\0'+encoded)
            existing = conn.execute('SELECT id,content_digest FROM events WHERE hub_id=? '
                                    'AND sender_event_id=?', (hub['id'], sender_id)).fetchone()
            if existing:
                if existing['content_digest'] != content:
                    raise APIError('event_id_conflict', 409)
                return {'id': existing['id'], 'duplicate': True}
            cursor = conn.execute('INSERT INTO events(home_id,hub_id,sender_event_id,kind,payload,'
                                  'content_digest,received_at) VALUES (?,?,?,?,?,?,?)',
                                  (hub['home_id'], hub['id'], sender_id, kind, encoded,
                                   content, self.clock()))
            return {'id': cursor.lastrowid, 'duplicate': False}

    def events(self, home, user, event=None):
        with self.transaction() as conn:
            self.access(conn, home, user)
            sql = 'SELECT id,hub_id,kind,payload,received_at FROM events WHERE home_id=?'
            params = [home]
            if event is not None:
                sql += ' AND id=?'
                params.append(event)
            rows = conn.execute(sql+' ORDER BY id DESC LIMIT 50', params).fetchall()
            if event is not None and not rows:
                raise APIError('not_found', 404)
            return [dict(row) | {'payload': json.loads(row['payload'])} for row in rows]
