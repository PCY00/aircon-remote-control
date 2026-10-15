"""Hub-reported device list (names, rooms, capability blocks, last state) for family screens."""

from __future__ import annotations

import json
import re
import unicodedata

from central_server.control import Controls
from central_server.households import APIError

BODY_BYTES = 32768  # the only route allowed past the app's 16 KiB body cap
MAX_DEVICES = 50
KEYS = frozenset({'id', 'name', 'room', 'type', 'capabilities', 'state', 'reported_at',
                  'controllable'})
TOKEN = re.compile(r'[a-z][a-z0-9_]{0,31}')
# Cc/Cf never reach family screens; Cs (lone surrogates) cannot even be stored as UTF-8.
HIDDEN = ('Cc', 'Cf', 'Cs')
STATEMENTS = (
    '''CREATE TABLE hub_inventory(
        hub_id TEXT PRIMARY KEY REFERENCES hubs(id), updated_at REAL NOT NULL)''',
    '''CREATE TABLE hub_devices(
        hub_id TEXT NOT NULL REFERENCES hubs(id), device_id TEXT NOT NULL,
        position INTEGER NOT NULL, name TEXT NOT NULL, room TEXT NOT NULL, type TEXT NOT NULL,
        capabilities TEXT NOT NULL, state TEXT NOT NULL, reported_at REAL,
        controllable INTEGER NOT NULL CHECK(controllable IN (0,1)),
        PRIMARY KEY(hub_id,device_id))''',
)


def invalid():
    return APIError('invalid_body', 400)


def cleaned(value, maximum, *, empty=False):
    # Like control heartbeat names: drop hidden characters instead of refusing the whole list.
    if not isinstance(value, str):
        raise invalid()
    value = ''.join(c for c in value if unicodedata.category(c) not in HIDDEN).strip()
    if not (0 if empty else 1) <= len(value) <= maximum:
        raise invalid()
    return value


def number(value, limit):
    # bool is an int subclass but a different value on screen; abs() <= limit also refuses NaN/inf.
    return not isinstance(value, bool) and isinstance(value, (int, float)) and abs(value) <= limit


def scalar(value):
    return (value is None or isinstance(value, bool) or number(value, 1e9)
            or (isinstance(value, str) and len(value) <= 40
                and not any(unicodedata.category(c) in HIDDEN for c in value)))


def validate(devices, now):
    """Return the normalized list; any malformed device refuses the whole report (400)."""
    if not isinstance(devices, list) or len(devices) > MAX_DEVICES:
        raise invalid()
    seen, result = set(), []
    for device in devices:
        if not isinstance(device, dict) or set(device) != KEYS:
            raise invalid()
        identifier, kind = device['id'], device['type']
        capabilities, state = device['capabilities'], device['state']
        reported = device['reported_at']
        # Unknown types, blocks and state keys are kept when well-formed: new devices need no
        # server change.
        if (not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{32}', identifier)
                or identifier in seen or not isinstance(kind, str) or not TOKEN.fullmatch(kind)
                or not isinstance(capabilities, list) or len(capabilities) > 16
                or not all(isinstance(c, str) and TOKEN.fullmatch(c) for c in capabilities)
                or len(set(capabilities)) != len(capabilities)
                or not isinstance(state, dict) or len(state) > 16
                or not all(TOKEN.fullmatch(key) and scalar(value) for key, value in state.items())
                or (reported is not None
                    and not (number(reported, 2**53) and 0 <= reported <= now+300))
                or type(device['controllable']) is not bool):
            raise invalid()
        seen.add(identifier)
        result.append({'id': identifier, 'name': cleaned(device['name'], 80),
                       'room': cleaned(device['room'], 40, empty=True), 'type': kind,
                       'capabilities': capabilities, 'state': state,
                       'reported_at': None if reported is None else float(reported),
                       'controllable': device['controllable']})
    return result


class Inventory(Controls):
    def replace(self, token, devices):
        with self.transaction(write=True) as conn:
            hub = self.hub(conn, token)
            # Each report is the hub's whole list: absent devices leave and the sent order is kept.
            conn.execute('DELETE FROM hub_devices WHERE hub_id=?', (hub['id'],))
            for position, device in enumerate(devices):
                conn.execute('INSERT INTO hub_devices VALUES (?,?,?,?,?,?,?,?,?,?)',
                             (hub['id'], device['id'], position, device['name'], device['room'],
                              device['type'], json.dumps(device['capabilities']),
                              json.dumps(device['state'], ensure_ascii=False, allow_nan=False),
                              device['reported_at'], int(device['controllable'])))
            conn.execute('INSERT INTO hub_inventory VALUES (?,?) ON CONFLICT(hub_id) '
                         'DO UPDATE SET updated_at=excluded.updated_at', (hub['id'], self.clock()))
            return {'status': 'stored', 'count': len(devices)}

    def devices(self, home, user):
        with self.transaction() as conn:
            self.access(conn, home, user)  # viewers included: reading never controls anything
            hub = conn.execute('SELECT b.id,c.last_seen,i.updated_at FROM hubs b '
                               'LEFT JOIN control_hubs c ON c.hub_id=b.id '
                               'LEFT JOIN hub_inventory i ON i.hub_id=b.id '
                               'WHERE b.home_id=? AND b.active=1', (home,)).fetchone()
            online = bool(hub and hub['last_seen'] is not None
                          and self.clock()-hub['last_seen'] < self.ONLINE_SECONDS)
            rows = conn.execute('SELECT * FROM hub_devices WHERE hub_id=? ORDER BY position',
                                (hub['id'] if hub else '',)).fetchall()
            devices = [{'id': row['device_id'], 'name': row['name'], 'room': row['room'],
                        'type': row['type'], 'capabilities': json.loads(row['capabilities']),
                        'state': json.loads(row['state']), 'reported_at': row['reported_at'],
                        'controllable': bool(row['controllable'])} for row in rows]
            return {'devices': devices, 'updated_at': hub['updated_at'] if hub else None,
                    'hub_online': online}
