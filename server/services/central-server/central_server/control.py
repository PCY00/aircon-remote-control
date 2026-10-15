"""Short-lived, household-scoped profile commands; never redeliver an uncertain send."""

import secrets
import time

from central_server.households import APIError, Households, token_digest

ALLOWED_ACTIONS = frozenset({
    'cool_on', 'power_off', 'mode_auto', 'mode_dry', 'mode_fan_only',
    'economy', 'turbo', 'led_toggle', 'airflow_fix', 'swing_toggle',
} | {f'cool_{temperature}_{fan}' for temperature in range(17, 31)
     for fan in ('auto', 'low', 'medium', 'high')})

STATEMENTS = (
    "CREATE TABLE control_hubs(hub_id TEXT PRIMARY KEY REFERENCES hubs(id), last_seen REAL NOT NULL)",
    """CREATE TABLE control_devices(
        hub_id TEXT NOT NULL REFERENCES hubs(id), device_id TEXT NOT NULL,
        name TEXT NOT NULL, active INTEGER NOT NULL, PRIMARY KEY(hub_id,device_id))""",
    """CREATE TABLE control_commands(
        id TEXT PRIMARY KEY, home_id TEXT NOT NULL REFERENCES homes(id),
        hub_id TEXT NOT NULL REFERENCES hubs(id), device_id TEXT NOT NULL,
        actor_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL,
        state TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
        updated_at REAL NOT NULL, attempt_token TEXT)""",
    "CREATE INDEX control_home_created ON control_commands(home_id,created_at)",
)


class Controls(Households):
    ONLINE_SECONDS = 25
    COMMAND_SECONDS = 30

    def __init__(self, database, *, clock=time.time):
        super().__init__(database, clock=clock)

    @staticmethod
    def hub(conn, token):
        row = conn.execute(
            'SELECT b.id,b.home_id FROM hubs b JOIN homes h ON h.id=b.home_id '
            'WHERE b.credential_digest=? AND b.active=1 AND h.active=1',
            (token_digest('hub', token),)).fetchone()
        if not row:
            raise APIError('invalid_hub_credentials', 401)
        return row

    @staticmethod
    def public(row):
        if row is None:
            return None
        return {key: row[key] for key in
                ('id', 'device_id', 'action', 'state', 'created_at', 'expires_at', 'updated_at')}

    def expire(self, conn, home, now=None):
        now = self.clock() if now is None else now
        conn.execute("UPDATE control_commands SET state='expired',updated_at=? "
                     "WHERE home_id=? AND state='queued' AND expires_at<=?", (now, home, now))
        # A delivery may have reached the Pi even when its result was lost.
        conn.execute("UPDATE control_commands SET state='unknown',updated_at=? "
                     "WHERE home_id=? AND state='dispatched' AND expires_at+20<=?", (now, home, now))

    def heartbeat(self, token, devices):
        with self.transaction(write=True) as conn:
            hub = self.hub(conn, token)
            conn.execute('INSERT INTO control_hubs VALUES(?,?) ON CONFLICT(hub_id) '
                         'DO UPDATE SET last_seen=excluded.last_seen', (hub['id'], self.clock()))
            # Rows follow the latest heartbeat (at most 20): absent devices leave the table.
            conn.execute('DELETE FROM control_devices WHERE hub_id=?', (hub['id'],))
            for device in devices:
                conn.execute('INSERT INTO control_devices VALUES(?,?,?,1) '
                             'ON CONFLICT(hub_id,device_id) DO UPDATE SET name=excluded.name,active=1',
                             (hub['id'], device['id'], device['name']))
            return {'status': 'ready'}

    def status(self, home, user):
        with self.transaction(write=True) as conn:
            role = self.access(conn, home, user)
            self.expire(conn, home)
            hub = conn.execute('SELECT b.id,c.last_seen FROM hubs b LEFT JOIN control_hubs c '
                               'ON c.hub_id=b.id WHERE b.home_id=? AND b.active=1', (home,)).fetchone()
            online = bool(hub and hub['last_seen'] is not None
                          and self.clock()-hub['last_seen'] < self.ONLINE_SECONDS)
            devices = [dict(row) for row in conn.execute(
                'SELECT device_id AS id,name FROM control_devices WHERE hub_id=? AND active=1 '
                'ORDER BY name,device_id', (hub['id'] if hub else '',))]
            latest = conn.execute('SELECT * FROM control_commands WHERE home_id=? '
                                  'ORDER BY created_at DESC,rowid DESC LIMIT 1', (home,)).fetchone()
            return {'online': online, 'can_control': role in ('owner', 'member'),
                    'actions': sorted(ALLOWED_ACTIONS),
                    'devices': devices, 'latest_command': self.public(latest)}

    def enqueue(self, home, user, request_id, device, action):
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            raise APIError('invalid_body', 400)
        with self.transaction(write=True) as conn:
            if self.access(conn, home, user) not in ('owner', 'member'):
                raise APIError('control_forbidden', 403)
            existing = conn.execute('SELECT * FROM control_commands WHERE id=?', (request_id,)).fetchone()
            if existing:
                if (existing['home_id'], existing['actor_id'], existing['device_id'], existing['action']) != (home, user, device, action):
                    raise APIError('control_request_conflict', 409)
                self.expire(conn, home)
                return self.public(conn.execute('SELECT * FROM control_commands WHERE id=?', (request_id,)).fetchone())
            self.expire(conn, home)
            hub = conn.execute('SELECT b.id,c.last_seen FROM hubs b JOIN control_hubs c ON c.hub_id=b.id '
                               'WHERE b.home_id=? AND b.active=1', (home,)).fetchone()
            if not hub or self.clock()-hub['last_seen'] >= self.ONLINE_SECONDS:
                raise APIError('control_offline', 503)
            if not conn.execute('SELECT 1 FROM control_devices WHERE hub_id=? AND device_id=? AND active=1',
                                (hub['id'], device)).fetchone():
                raise APIError('control_device_unavailable', 404)
            if conn.execute("SELECT 1 FROM control_commands WHERE home_id=? AND state IN ('queued','dispatched')", (home,)).fetchone():
                raise APIError('control_busy', 409)
            if conn.execute('SELECT 1 FROM control_commands WHERE home_id=? AND created_at>?', (home, self.clock()-3)).fetchone():
                raise APIError('control_rate_limit', 429)
            now = self.clock()
            conn.execute("INSERT INTO control_commands VALUES(?,?,?,?,?,?,'queued',?,?,?,NULL)",
                         (request_id, home, hub['id'], device, user, action, now, now+self.COMMAND_SECONDS, now))
            self.audit(conn, home, user, 'aircon_'+action+'_requested')
            # Bound old history without discarding pending or uncertain commands.
            conn.execute("DELETE FROM control_commands WHERE home_id=? AND state NOT IN ('queued','dispatched') "
                         "AND id NOT IN (SELECT id FROM control_commands WHERE home_id=? ORDER BY created_at DESC LIMIT 200)", (home, home))
            return self.public(conn.execute('SELECT * FROM control_commands WHERE id=?', (request_id,)).fetchone())

    def command(self, home, user, command):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user)
            self.expire(conn, home)
            row = conn.execute('SELECT * FROM control_commands WHERE id=? AND home_id=?', (command, home)).fetchone()
            if not row:
                raise APIError('not_found', 404)
            return self.public(row)

    def next(self, token):
        with self.transaction(write=True) as conn:
            hub = self.hub(conn, token)
            # One clock reading: a row that survives expiry must still have time left when delivered.
            now = self.clock()
            self.expire(conn, hub['home_id'], now)
            rows = conn.execute("SELECT * FROM control_commands WHERE hub_id=? AND state='queued' AND expires_at>? ORDER BY created_at", (hub['id'], now)).fetchall()
            for row in rows:
                try:
                    role = self.access(conn, row['home_id'], row['actor_id'])
                except APIError:
                    role = None
                device = conn.execute('SELECT 1 FROM control_devices WHERE hub_id=? AND device_id=? AND active=1', (hub['id'], row['device_id'])).fetchone()
                if role not in ('owner', 'member') or not device:
                    conn.execute("UPDATE control_commands SET state='cancelled',updated_at=? WHERE id=?", (now, row['id']))
                    continue
                attempt = secrets.token_hex(32)
                conn.execute("UPDATE control_commands SET state='dispatched',attempt_token=?,updated_at=? WHERE id=?", (attempt, now, row['id']))
                return {'command': {**self.public(row), 'attempt_token': attempt,
                                    'state': 'dispatched', 'remaining_seconds': min(self.COMMAND_SECONDS, row['expires_at']-now)}}
            return {'command': None}

    def result(self, token, command, attempt, state):
        with self.transaction(write=True) as conn:
            hub = self.hub(conn, token)
            row = conn.execute('SELECT * FROM control_commands WHERE id=? AND hub_id=?', (command, hub['id'])).fetchone()
            if not row or not row['attempt_token'] or not secrets.compare_digest(row['attempt_token'], attempt):
                raise APIError('not_found', 404)
            if row['state'] not in ('dispatched', 'unknown', state):
                raise APIError('control_result_conflict', 409)
            conn.execute('UPDATE control_commands SET state=?,updated_at=? WHERE id=?', (state, self.clock(), command))
            return {'status': 'recorded'}
