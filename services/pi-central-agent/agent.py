"""Read existing Pi histories without modifying them; relay through a private durable queue."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER = logging.getLogger(__name__)
SOURCES = {
    "door": ("sensors/sensors.sqlite3", "door_events"),
    "automation": ("automations/automations.sqlite3", "automation_events"),
}


def timestamp(value):
    resolved = datetime.fromisoformat(value)
    if resolved.tzinfo is None:
        raise ValueError("Source timestamp must have an offset")
    return resolved.timestamp()


def endpoint(value):
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.port not in (None, 443)
    ):
        raise ValueError("An approved HTTPS origin is required")
    return value.rstrip("/")


def load_config(path):
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("Configuration must be private")
    value = json.loads(path.read_text())
    if set(value) != {"endpoint", "hub_token", "source_data_dir"}:
        raise ValueError("Unknown private configuration")
    value["endpoint"] = endpoint(value["endpoint"])
    if not re.fullmatch(r"hub_[A-Za-z0-9_-]{32,128}", value["hub_token"]):
        raise ValueError("An individual hub credential is required")
    source = Path(value["source_data_dir"])
    if not source.is_absolute() or not source.is_dir():
        raise ValueError("Verified existing source directory is required")
    return value


class SourceChangedError(RuntimeError):
    """An operator must inspect a replaced/reset source rather than replay its history."""


class QueueFullError(RuntimeError):
    """Preserve the cursor and source history until bounded capacity is available."""


class Store:
    def __init__(self, path, *, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS identity(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS cursors(
                    source TEXT PRIMARY KEY, file_identity TEXT NOT NULL, last_id INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS outbox(
                    event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                    expires_at REAL NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
                    due_at REAL NOT NULL);
            """)
            if not conn.execute("SELECT id FROM identity").fetchone():
                conn.execute("INSERT INTO identity VALUES(?)", (str(uuid.uuid4()),))
        self.path.chmod(0o600)

    @contextlib.contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _enqueue(self, conn, event_id, kind, payload, expires):
        if conn.execute("SELECT 1 FROM outbox WHERE event_id=?", (event_id,)).fetchone():
            return
        if conn.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0] >= 1000:
            raise QueueFullError("Pending queue capacity reached")
        conn.execute(
            "INSERT INTO outbox VALUES(?,?,?,?,'pending',0,?)",
            (event_id, kind, json.dumps(payload, sort_keys=True), expires, self.clock()),
        )

    def connection_test(self):
        # A real connection test is distinct from a fabricated sensor transition.
        now = self.clock()
        with self.connect() as conn:
            self._enqueue(
                conn,
                str(uuid.uuid4()),
                "hub.connection_test",
                {
                    "source": "raspberry_pi_agent",
                    "status": "connected",
                    "notification_expires_at": now + 240,
                },
                now + 240,
            )

    def collect(self, directory):
        counts = {"baseline": 0, "queued": 0, "expired": 0, "invalid": 0}
        for source, (relative, table) in SOURCES.items():
            path = Path(directory) / relative
            if not path.is_file():
                raise FileNotFoundError("An expected source database is unavailable")
            info = path.stat()
            identity = str(info.st_dev) + ":" + str(info.st_ino)
            src = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
            src.row_factory = sqlite3.Row
            try:
                with self.connect() as conn:
                    previous = conn.execute(
                        "SELECT * FROM cursors WHERE source=?", (source,)
                    ).fetchone()
                    maximum = src.execute("SELECT COALESCE(MAX(id),0) FROM " + table).fetchone()[0]
                    if previous is None:
                        conn.execute(
                            "INSERT INTO cursors VALUES(?,?,?)", (source, identity, maximum)
                        )
                        counts["baseline"] += 1
                        continue
                    if previous["file_identity"] != identity or maximum < previous["last_id"]:
                        raise SourceChangedError("Source reset/replacement requires inspection")
                    namespace = conn.execute("SELECT id FROM identity").fetchone()[0]
                    rows = src.execute(
                        "SELECT * FROM " + table + " WHERE id>? ORDER BY id LIMIT 50",
                        (previous["last_id"],),
                    ).fetchall()
                    for row in rows:
                        try:
                            occurred = timestamp(row["occurred_at"])
                            if not math.isfinite(occurred) or occurred > self.clock() + 30:
                                raise ValueError("Invalid/future source timestamp")
                            expires = occurred + 240
                            if expires <= self.clock():
                                counts["expired"] += 1
                            else:
                                if source == "door":
                                    if row["state"] not in ("open", "closed"):
                                        raise ValueError("Unexpected door state")
                                    kind = "sensor.door_changed"
                                    payload = {
                                        "state": row["state"],
                                        "previous_state": (
                                            row["previous_state"]
                                            if row["previous_state"] in ("open", "closed")
                                            else None
                                        ),
                                    }
                                else:
                                    if row["event_type"] not in (
                                        "warning_triggered",
                                        "warning_resolved",
                                    ):
                                        raise ValueError("Unexpected automation event")
                                    kind = "automation." + row["event_type"]
                                    payload = {"status": row["event_type"]}
                                # Don't export MAC addresses, room names or raw MQTT payloads.
                                payload.update(
                                    source=source,
                                    occurred_at=row["occurred_at"],
                                    notification_expires_at=expires,
                                )
                                stable = hashlib.sha256(
                                    (namespace + ":" + source + ":" + str(row["id"])).encode()
                                ).hexdigest()
                                self._enqueue(conn, stable, kind, payload, expires)
                                counts["queued"] += 1
                        except (ValueError, TypeError, OverflowError):
                            counts["invalid"] += 1
                        conn.execute(
                            "UPDATE cursors SET last_id=? WHERE source=?", (row["id"], source)
                        )
            finally:
                src.close()
        return counts

    def next(self):
        with self.connect() as conn:
            conn.execute(
                "UPDATE outbox SET state='expired' WHERE state='pending' AND expires_at<=?",
                (self.clock(),),
            )
            conn.execute(
                "DELETE FROM outbox WHERE state!='pending' AND event_id NOT IN "
                "(SELECT event_id FROM outbox WHERE state!='pending' "
                "ORDER BY due_at DESC LIMIT 100)"
            )
            row = conn.execute(
                "SELECT * FROM outbox WHERE state='pending' AND due_at<=? ORDER BY due_at LIMIT 1",
                (self.clock(),),
            ).fetchone()
            return dict(row) if row else None

    def finish(self, item, outcome):
        attempts = item["attempts"] + 1
        state = "pending" if outcome == "retry" else outcome
        if state == "pending" and attempts >= 8:
            state = "failed"
        with self.connect() as conn:
            conn.execute(
                "UPDATE outbox SET state=?,attempts=?,due_at=? WHERE event_id=?",
                (state, attempts, self.clock() + min(120, 5 * 2**attempts), item["event_id"]),
            )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Sender:
    def __init__(self, config):
        self.url = endpoint(config["endpoint"]) + "/v1/hub/events"
        self.token = config["hub_token"]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.blocked = False

    def send(self, item):
        body = {
            "event_id": item["event_id"],
            "kind": item["kind"],
            "payload": json.loads(item["payload"]),
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                reply = json.loads(response.read(8193))
                if (
                    response.status == 200
                    and type(reply.get("id")) is int
                    and type(reply.get("duplicate")) is bool
                ):
                    return "accepted"
                return "retry"
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                self.blocked = True
                return "rejected"
            if error.code == 429 or error.code >= 500:
                return "retry"
            return "rejected"
        except Exception:
            # Never log the URL, authorization header, sensor content or provider body.
            return "retry"


def dispatch(store, sender):
    if sender.blocked:
        return False
    item = store.next()
    if item is None:
        return False
    outcome = sender.send(item)
    store.finish(item, outcome)
    LOGGER.info("CENTRAL_RELAY outcome=%s", outcome)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config/aircon-central-agent/config.json"
    )
    parser.add_argument(
        "--state", type=Path, default=Path.home() / ".local/state/aircon-central-agent"
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--connection-test", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    args.state.mkdir(mode=0o700, parents=True, exist_ok=True)
    handler = RotatingFileHandler(args.state / "agent.log", maxBytes=1048576, backupCount=3)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    try:
        import fcntl

        with (args.state / "agent.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            config = load_config(args.config)
            store = Store(args.state / "outbox.sqlite3")
            sender = Sender(config)
            if args.connection_test:
                store.connection_test()
            failures = 0
            while True:
                try:
                    counts = store.collect(config["source_data_dir"])
                    if any(counts.values()):
                        LOGGER.info(
                            "SOURCE_COLLECTION counts=%s", json.dumps(counts, sort_keys=True)
                        )
                    dispatch(store, sender)
                    failures = 0
                except (SourceChangedError, QueueFullError):
                    # Still try to empty the queue; don't rebaseline or overwrite source history.
                    LOGGER.error("SOURCE_INSPECTION_REQUIRED")
                    dispatch(store, sender)
                    failures += 1
                except (OSError, sqlite3.Error):
                    LOGGER.warning("SOURCE_TEMPORARILY_UNAVAILABLE")
                    failures += 1
                if sender.blocked:
                    LOGGER.error("HUB_AUTHENTICATION_REQUIRES_INSPECTION")
                    raise RuntimeError("Hub credential rejected")
                if args.once:
                    if failures:
                        raise RuntimeError("Source inspection failed")
                    print("AGENT_ONCE=PASS SOURCE_HISTORY_UNMODIFIED=TRUE")
                    return
                if failures >= 5:
                    raise RuntimeError("Repeated source failure requires inspection")
                time.sleep(5)
    except Exception as error:
        LOGGER.error("AGENT_STOPPED kind=%s", type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
