"""Transactional household schema added to the existing runtime database."""

STATEMENTS = (
    '''CREATE TABLE users (
        id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
        email TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        UNIQUE(issuer,subject), UNIQUE(email))''',
    '''CREATE TABLE homes (
        id TEXT PRIMARY KEY, name TEXT NOT NULL,
        owner_id TEXT NOT NULL REFERENCES users(id))''',
    '''CREATE TABLE audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        home_id TEXT REFERENCES homes(id), actor_id TEXT REFERENCES users(id),
        kind TEXT NOT NULL, created_at REAL NOT NULL)''',
    '''CREATE TABLE memberships (
        home_id TEXT NOT NULL REFERENCES homes(id), user_id TEXT NOT NULL REFERENCES users(id),
        role TEXT NOT NULL CHECK(role IN ('owner','member','viewer')),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), revoked_seq INTEGER,
        PRIMARY KEY(home_id,user_id))''',
    '''CREATE INDEX membership_user_active ON memberships(user_id,active)''',
    '''CREATE TABLE invitations (
        digest TEXT PRIMARY KEY, home_id TEXT NOT NULL REFERENCES homes(id),
        email TEXT NOT NULL, target_id TEXT REFERENCES users(id),
        role TEXT NOT NULL CHECK(role IN ('member','viewer')),
        created_seq INTEGER NOT NULL REFERENCES audit(id), expires_at REAL NOT NULL,
        consumed INTEGER NOT NULL DEFAULT 0 CHECK(consumed IN (0,1)))''',
    '''CREATE TABLE hubs (
        id TEXT PRIMARY KEY, credential_digest TEXT NOT NULL UNIQUE,
        claim_digest TEXT UNIQUE, claim_expires_at REAL NOT NULL,
        home_id TEXT REFERENCES homes(id), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))''',
    '''CREATE UNIQUE INDEX home_one_active_hub ON hubs(home_id)
       WHERE home_id IS NOT NULL AND active=1''',
    '''CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, home_id TEXT NOT NULL REFERENCES homes(id),
        hub_id TEXT NOT NULL REFERENCES hubs(id), sender_event_id TEXT NOT NULL,
        kind TEXT NOT NULL, payload TEXT NOT NULL, content_digest TEXT NOT NULL,
        received_at REAL NOT NULL, UNIQUE(hub_id,sender_event_id))''',
    '''CREATE INDEX events_home_id ON events(home_id,id)''',
)
