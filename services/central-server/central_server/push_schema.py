"""Additive migration; existing homes, identities and events are preserved."""

PUSH_STATEMENTS = (
    """CREATE TABLE installations (
        id TEXT PRIMARY KEY, secret_digest TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(id), token TEXT UNIQUE,
        binding TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
        updated_at REAL NOT NULL)""",
    """CREATE TABLE push_messages (
        id TEXT PRIMARY KEY, home_id TEXT NOT NULL REFERENCES homes(id),
        event_id INTEGER UNIQUE REFERENCES events(id),
        kind TEXT NOT NULL CHECK(kind IN ('event','test')),
        created_at REAL NOT NULL, expires_at REAL NOT NULL)""",
    """CREATE TABLE push_jobs (
        message_id TEXT NOT NULL REFERENCES push_messages(id),
        installation_id TEXT NOT NULL REFERENCES installations(id),
        binding TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
        state TEXT NOT NULL CHECK(state IN ('pending','sending','accepted','cancelled','failed')),
        attempts INTEGER NOT NULL DEFAULT 0, due_at REAL NOT NULL,
        lease_until REAL NOT NULL DEFAULT 0, last_error TEXT,
        PRIMARY KEY(message_id,installation_id))""",
    """CREATE INDEX push_jobs_due ON push_jobs(state,due_at)""",
)
