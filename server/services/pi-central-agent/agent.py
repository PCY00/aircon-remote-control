"""Read existing Pi histories without modifying them; relay through a private durable queue."""

from __future__ import annotations

import argparse
import contextlib
import email.utils
import hashlib
import ipaddress
import json
import logging
import math
import os
import re
import sqlite3
import stat
import time
import unicodedata
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
# A flapping (or spoofed MQTT) sensor relays at most this many transitions per window. Later ones
# are coalesced: one deferred event per sensor always carries the latest transition, superseded
# intermediate transitions are dropped, and every row still advances the cursor.
RELAY_BUDGET_WINDOW = 300.0
RELAY_BUDGET_TRANSITIONS = 10
RELAY_COALESCE_DELAY = 60.0
RELAY_COALESCE_MARGIN = 5.0  # a held slot is due this long before its own expiry at the latest
# Climate reports are state snapshots: at most one relay per sensor per interval (report time);
# skipped reports still move the cursor. Door/warning transitions always go out before them.
CLIMATE_MIN_INTERVAL = 60.0
# 429 from the central server is transient: every pending event is held for Retry-After seconds
# (minimum, default when absent, maximum); it is neither an attempt nor a failure.
RATE_LIMIT_WAIT = (1.0, 30.0, 300.0)
# Cloudflare blocks Python's default User-Agent: every central request names this client.
USER_AGENT = "FamilySmartHome-Pi/0.7.0"
# Capability inventory (design decision 0019). From 0.7.0 device and room names leave the Pi (user
# approval 2026-10-16); Zigbee addresses, MQTT friendly names/topics and raw payloads never do.
INVENTORY_MAX_DEVICES = 50
INVENTORY_MAX_BYTES = 32768
INVENTORY_MIN_INTERVAL = 15.0  # never two inventory attempts closer than this
INVENTORY_REFRESH_INTERVAL = 300.0  # an unchanged list is still sent this often
INVENTORY_MISSING_ROUTE_WAIT = 3600.0  # 404: a central server older than the inventory route
INVENTORY_RETRY_WAIT = 60.0  # network error or 5xx
INVENTORY_REJECTED_WAIT = 300.0  # another 4xx: the same list would be refused again
AIRCON_CAPABILITIES = ("power", "setpoint", "mode", "fan", "actions")
# Pi sensor kind -> (inventory type, capabilities without battery, Pi app's default display name)
SENSOR_TYPES = {
    "door_contact": ("door_sensor", ("contact",), "문 열림 센서"),
    "temperature_humidity": ("climate_sensor", ("temperature", "humidity"), "온·습도 센서"),
}
ZIGBEE_ADDRESS = re.compile(r"0x[0-9a-fA-F]{16}")


def timestamp(value):
    resolved = datetime.fromisoformat(value)
    if resolved.tzinfo is None:
        raise ValueError("Source timestamp must have an offset")
    return resolved.timestamp()


def device_ref(namespace, sensor_id):
    """Inventory and event id of a Pi sensor; its Zigbee friendly name never leaves the Pi."""
    return hashlib.sha256((namespace + ":device:" + str(sensor_id)).encode()).hexdigest()[:32]


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
    if set(value) not in ({"endpoint", "hub_token", "source_data_dir"},
                          {"endpoint", "hub_token", "source_data_dir", "control_origin"}):
        raise ValueError("Unknown private configuration")
    value["endpoint"] = endpoint(value["endpoint"])
    if not re.fullmatch(r"hub_[A-Za-z0-9_-]{32,128}", value["hub_token"]):
        raise ValueError("An individual hub credential is required")
    source = Path(value["source_data_dir"])
    if not source.is_absolute() or not source.is_dir():
        raise ValueError("Verified existing source directory is required")
    if "control_origin" in value:
        value["control_origin"] = control_origin(value["control_origin"])
    return value


def control_origin(value):
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname
    if (parsed.scheme != 'http' or not host or parsed.port != 8001
            or parsed.username or parsed.password or parsed.path not in ('', '/')
            or parsed.query or parsed.fragment):
        raise ValueError('Verified local controller origin on port 8001 required')
    if host != 'localhost':
        address = ipaddress.ip_address(host)
        if not (address.is_loopback or address in ipaddress.ip_network('100.64.0.0/10')):
            raise ValueError('Controller must use loopback or the verified Pi Tailscale address')
    return value.rstrip('/')


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
                CREATE TABLE IF NOT EXISTS climate_source(file_identity TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS climate_cursors(
                    sensor_ref TEXT PRIMARY KEY, reported_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS control_receipts(
                    id TEXT PRIMARY KEY, attempt_token TEXT NOT NULL, state TEXT NOT NULL,
                    created_at REAL NOT NULL, reported INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS relay_budget(
                    sensor_ref TEXT PRIMARY KEY, window_start REAL NOT NULL,
                    relayed INTEGER NOT NULL, dropped INTEGER NOT NULL, deferred_event_id TEXT);
            """)
            # Additive migration for outboxes created before climate relay intervals existed.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(climate_cursors)")}
            if "relayed_at" not in columns:
                conn.execute("ALTER TABLE climate_cursors ADD COLUMN relayed_at REAL")
            # A process may have stopped after sending IR and before saving its result.
            conn.execute("UPDATE control_receipts SET state='unknown' WHERE state='executing'")
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

    def namespace(self):
        """This agent's private hashing namespace (sensor refs, event ids and inventory ids)."""
        with self.connect() as conn:
            return conn.execute("SELECT id FROM identity").fetchone()[0]

    def _enqueue(self, conn, event_id, kind, payload, expires, due=None):
        if conn.execute("SELECT 1 FROM outbox WHERE event_id=?", (event_id,)).fetchone():
            return
        if conn.execute("SELECT COUNT(*) FROM outbox WHERE state='pending'").fetchone()[0] >= 1000:
            raise QueueFullError("Pending queue capacity reached")
        conn.execute(
            "INSERT INTO outbox VALUES(?,?,?,?,'pending',0,?)",
            (event_id, kind, json.dumps(payload, sort_keys=True), expires,
             self.clock() if due is None else due),
        )

    def _relay(self, conn, sensor, event_id, kind, payload, expires):
        """Budgeted relay. Returns ("queued"|"coalesced", transitions dropped in this window)."""
        now = self.clock()
        budget = conn.execute("SELECT * FROM relay_budget WHERE sensor_ref=?", (sensor,)).fetchone()
        if budget is None or now - budget["window_start"] >= RELAY_BUDGET_WINDOW:
            budget = {"window_start": now, "relayed": 0, "dropped": 0,
                      "deferred_event_id": budget["deferred_event_id"] if budget else None}
        relayed, dropped = budget["relayed"], budget["dropped"]
        deferred = budget["deferred_event_id"]
        if relayed < RELAY_BUDGET_TRANSITIONS:
            # A fresher transition goes out now; one still held from the last window is stale.
            if deferred and conn.execute(
                "DELETE FROM outbox WHERE event_id=? AND state='pending'", (deferred,)
            ).rowcount:
                dropped += 1
            self._enqueue(conn, event_id, kind, payload, expires)
            outcome, relayed, deferred = "queued", relayed + 1, None
        elif deferred and conn.execute(
            "SELECT 1 FROM outbox WHERE event_id=? AND state='pending'", (deferred,)
        ).fetchone():
            # Not sent yet: the held transition is superseded by this latest one (same slot).
            conn.execute(
                "UPDATE outbox SET event_id=?,kind=?,payload=?,expires_at=? WHERE event_id=?",
                (event_id, kind, json.dumps(payload, sort_keys=True), expires, deferred),
            )
            outcome, dropped, deferred = "coalesced", dropped + 1, event_id
        else:
            # The latest transition waits for the burst to settle, but never past its own expiry
            # (a restart backlog carries rows that are already old): then it goes out at once.
            due = max(now, min(now + RELAY_COALESCE_DELAY, expires - RELAY_COALESCE_MARGIN))
            self._enqueue(conn, event_id, kind, payload, expires, due)
            outcome, deferred = "queued", event_id
        conn.execute(
            "INSERT INTO relay_budget VALUES(?,?,?,?,?) ON CONFLICT(sensor_ref) DO UPDATE SET "
            "window_start=excluded.window_start,relayed=excluded.relayed,"
            "dropped=excluded.dropped,deferred_event_id=excluded.deferred_event_id",
            (sensor, budget["window_start"], relayed, dropped, deferred),
        )
        return outcome, dropped

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
        counts = {"baseline": 0, "queued": 0, "coalesced": 0, "expired": 0, "invalid": 0}
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
                    coalesced = {}
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
                                        # The hashed inventory id, never the Zigbee friendly name.
                                        "device_id": device_ref(namespace, row["device_id"]),
                                    }
                                else:
                                    if row["event_type"] not in (
                                        "warning_triggered",
                                        "warning_resolved",
                                    ):
                                        raise ValueError("Unexpected automation event")
                                    kind = "automation." + row["event_type"]
                                    payload = {"status": row["event_type"]}
                                # Events carry no names, rooms, MAC addresses or raw MQTT payloads.
                                # Names and rooms leave the Pi only in the inventory (approved
                                # 2026-10-16); the app joins them through the hashed device_id.
                                payload.update(
                                    source=source,
                                    occurred_at=row["occurred_at"],
                                    notification_expires_at=expires,
                                )
                                stable = hashlib.sha256(
                                    (namespace + ":" + source + ":" + str(row["id"])).encode()
                                ).hexdigest()
                                # Budget key: the door sensor, or the automation source as a whole.
                                sensor = hashlib.sha256((
                                    namespace + ":budget:" + source + ":"
                                    + (str(row["device_id"]) if source == "door" else "")
                                ).encode()).hexdigest()
                                outcome, dropped = self._relay(
                                    conn, sensor, stable, kind, payload, expires
                                )
                                counts[outcome] += 1
                                if outcome == "coalesced":
                                    coalesced[sensor] = dropped
                        except (ValueError, TypeError, OverflowError):
                            counts["invalid"] += 1
                        conn.execute(
                            "UPDATE cursors SET last_id=? WHERE source=?", (row["id"], source)
                        )
                    for sensor, dropped in coalesced.items():
                        log_limited("coalesce:" + sensor, logging.WARNING,
                                    "RELAY_COALESCED sensor=%s dropped=%s", sensor[:12], dropped)
            finally:
                src.close()
        counts.update(self.collect_climate(directory))
        return counts

    def collect_climate(self, directory):
        counts = {
            "climate_baseline": 0,
            "climate_queued": 0,
            "climate_skipped": 0,
            "climate_expired": 0,
            "climate_invalid": 0,
        }
        path = Path(directory) / "sensors/sensors.sqlite3"
        info = path.stat()
        identity = str(info.st_dev) + ":" + str(info.st_ino)
        src = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
        src.row_factory = sqlite3.Row
        try:
            # Older fixture/source layouts can contain door history only.
            if not src.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sensor_states'"
            ).fetchone():
                return counts
            rows = src.execute(
                "SELECT device_id,state_json,last_reported_at FROM sensor_states "
                "WHERE kind='temperature_humidity'"
            ).fetchall()
            with self.connect() as conn:
                previous = conn.execute("SELECT file_identity FROM climate_source").fetchone()
                if previous and previous["file_identity"] != identity:
                    raise SourceChangedError("Climate source replacement requires inspection")
                baseline = previous is None
                if baseline:
                    conn.execute("INSERT INTO climate_source VALUES(?)", (identity,))
                namespace = conn.execute("SELECT id FROM identity").fetchone()[0]
                for row in rows:
                    sensor = hashlib.sha256(
                        (namespace + ":climate:" + row["device_id"]).encode()
                    ).hexdigest()
                    old = conn.execute(
                        "SELECT reported_at,relayed_at FROM climate_cursors WHERE sensor_ref=?",
                        (sensor,),
                    ).fetchone()
                    try:
                        occurred = timestamp(row["last_reported_at"])
                        if not math.isfinite(occurred) or occurred > self.clock() + 30:
                            raise ValueError("Invalid climate report time")
                        if old and occurred <= old["reported_at"]:
                            continue
                        values = json.loads(row["state_json"])
                        payload = {}
                        for key, minimum, maximum in (
                            ("temperature_c", -100, 150),
                            ("humidity_percent", 0, 100),
                        ):
                            value = values.get(key)
                            if value is not None:
                                if (
                                    isinstance(value, bool)
                                    or not isinstance(value, (float, int))
                                    or not math.isfinite(value)
                                    or not minimum <= value <= maximum
                                ):
                                    raise ValueError("Invalid climate measurement")
                                payload[key] = value
                        if not payload:
                            raise ValueError("No climate measurement")
                        expires = occurred + 240
                        relayed = old["relayed_at"] if old else None
                        if baseline:
                            counts["climate_baseline"] += 1
                        elif expires <= self.clock():
                            counts["climate_expired"] += 1
                        elif relayed is not None and occurred - relayed < CLIMATE_MIN_INTERVAL:
                            counts["climate_skipped"] += 1
                        else:
                            payload.update(
                                source="climate",
                                sensor_ref=sensor,
                                device_id=device_ref(namespace, row["device_id"]),
                                occurred_at=row["last_reported_at"],
                                notification_expires_at=expires,
                            )
                            stable = hashlib.sha256(
                                (sensor + ":" + str(occurred)).encode()
                            ).hexdigest()
                            self._enqueue(conn, stable, "sensor.climate_report", payload, expires)
                            counts["climate_queued"] += 1
                            relayed = occurred
                        conn.execute(
                            "INSERT INTO climate_cursors VALUES(?,?,?) ON CONFLICT(sensor_ref) "
                            "DO UPDATE SET reported_at=excluded.reported_at,"
                            "relayed_at=excluded.relayed_at",
                            (sensor, occurred, relayed),
                        )
                    except (ValueError, TypeError, OverflowError, AttributeError):
                        # Invalid measurements are not sent; an unchanged invalid report is retried
                        # only at the normal polling interval and never grows the outbox.
                        counts["climate_invalid"] += 1
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
            # Transitions and warnings before climate snapshots, also when a 429 hold ends.
            row = conn.execute(
                "SELECT * FROM outbox WHERE state='pending' AND due_at<=? "
                "ORDER BY kind='sensor.climate_report', due_at LIMIT 1",
                (self.clock(),),
            ).fetchone()
            return dict(row) if row else None

    def finish(self, item, outcome, *, wait=0.0):
        if outcome == "rate_limited":
            # Hold every pending event (this one included) until Retry-After passes. Nothing is
            # dropped, nothing is sent twice, and the attempt budget is not consumed.
            with self.connect() as conn:
                conn.execute("UPDATE outbox SET due_at=MAX(due_at,?) WHERE state='pending'",
                             (self.clock() + wait,))
            return
        attempts = item["attempts"] + 1
        state = "pending" if outcome == "retry" else outcome
        if state == "pending" and attempts >= 8:
            state = "failed"
        with self.connect() as conn:
            conn.execute(
                "UPDATE outbox SET state=?,attempts=?,due_at=? WHERE event_id=?",
                (state, attempts, self.clock() + min(120, 5 * 2**attempts), item["event_id"]),
            )

    def begin_control(self, command):
        with self.connect() as conn:
            cursor = conn.execute("INSERT OR IGNORE INTO control_receipts(id,attempt_token,state,created_at) "
                                  "VALUES(?,?,'executing',?)", (command['id'], command['attempt_token'], self.clock()))
            return cursor.rowcount == 1

    def finish_control(self, command, state):
        with self.connect() as conn:
            conn.execute('UPDATE control_receipts SET state=? WHERE id=?', (state, command['id']))

    def pending_result(self):
        with self.connect() as conn:
            conn.execute('UPDATE control_receipts SET reported=1 WHERE created_at<?', (self.clock()-600,))
            conn.execute('DELETE FROM control_receipts WHERE reported=1 AND id NOT IN '
                         '(SELECT id FROM control_receipts ORDER BY created_at DESC LIMIT 200)')
            row = conn.execute("SELECT * FROM control_receipts WHERE reported=0 AND state!='executing' ORDER BY created_at LIMIT 1").fetchone()
            return dict(row) if row else None

    def reported_control(self, command):
        with self.connect() as conn:
            conn.execute('UPDATE control_receipts SET reported=1 WHERE id=?', (command['id'],))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def retry_after(headers):
    """Retry-After as delta-seconds or an HTTP-date; otherwise the default. Always within bounds."""
    low, default, high = RATE_LIMIT_WAIT
    value = str((headers.get("Retry-After") if headers is not None else None) or "").strip()
    try:
        if re.fullmatch(r"[0-9]{1,9}", value):
            wait = float(value)
        elif value:
            wait = email.utils.parsedate_to_datetime(value).timestamp() - time.time()
        else:
            wait = default
    except (TypeError, ValueError, OverflowError):
        wait = default
    return min(max(wait, low), high)


class Sender:
    def __init__(self, config):
        self.url = endpoint(config["endpoint"]) + "/v1/hub/events"
        self.token = config["hub_token"]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.blocked = False
        self.rate_limit_wait = 0.0

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
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json",
                     "User-Agent": USER_AGENT},
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                reply = json.loads(response.read(8193))
                if (
                    response.status in (200, 202)
                    and type(reply.get("id")) is int
                    and type(reply.get("duplicate")) is bool
                ):
                    return "accepted"
                return "retry"
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                self.blocked = True
                return "rejected"
            if error.code == 429:
                self.rate_limit_wait = retry_after(error.headers)
                return "rate_limited"
            if error.code >= 500:
                return "retry"
            return "rejected"
        except Exception:
            # Never log the URL, authorization header, sensor content or provider body.
            return "retry"


CONTROL_PAYLOADS = {
    'cool_on': {'action': 'set_state', 'power': True, 'mode': 'cool', 'temperature_c': 24, 'fan': 'auto'},
    'power_off': {'action': 'set_state', 'power': False},
    **{f'cool_{temperature}_{fan}': {'action': 'set_state', 'power': True, 'mode': 'cool',
                                   'temperature_c': temperature, 'fan': fan}
       for temperature in range(17, 31) for fan in ('auto', 'low', 'medium', 'high')},
    **{command: {'action': 'execute', 'command_id': command} for command in
       ('mode_auto', 'mode_dry', 'mode_fan_only', 'economy', 'turbo', 'led_toggle', 'airflow_fix', 'swing_toggle')},
}


def control_devices(rows):
    """The control heartbeat list: reviewed profile with an H2 IR binding, at most 20."""
    # Same Cc/Cf stripping as the server's heartbeat: one odd name must not reject it.
    return [{'id': row['id'], 'name': ''.join(c for c in str(row.get('name') or '')
                                               if unicodedata.category(c) not in ('Cc', 'Cf')
                                               ).strip()[:80].strip() or 'Air conditioner'}
            for row in rows if isinstance(row, dict)
            and re.fullmatch(r'[a-f0-9]{32}', str(row.get('id', '')))
            and row.get('profile_id') == 'air_conditioner/Carrier/CS-A061GS'
            and isinstance(row.get('zigbee_binding'), dict)
            and row['zigbee_binding'].get('type') == 'h2_ir'][:20]


def clean_text(value, limit):
    """The server's text rules: Cc/Cf (and lone surrogates) removed, trimmed, at most `limit`."""
    if not isinstance(value, str):
        return ''
    text = ''.join(c for c in value if unicodedata.category(c) not in ('Cc', 'Cf', 'Cs'))
    return text.strip()[:limit].strip()


def clean_label(value, limit, private=()):
    """A user label, or '' when it repeats a Zigbee friendly name or address (never sent)."""
    text = clean_text(value, limit)
    if ZIGBEE_ADDRESS.search(text) or any(
        isinstance(hidden, str) and clean_text(hidden, limit)
        and text.casefold() == clean_text(hidden, limit).casefold()
        for hidden in private
    ):
        return ''
    return text


def clean_number(value, minimum, maximum):
    """A finite number inside the given range (bool is not a number here), else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and minimum <= value <= maximum else None
    except OverflowError:  # an int too large for a float
        return None


def reported_epoch(value, now):
    """ISO time with an offset -> epoch seconds; missing, invalid or future (>60 s) -> None."""
    try:
        moment = timestamp(value)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    if not math.isfinite(moment) or moment <= 0 or moment > now + 60:
        return None
    return round(moment, 3)


def build_inventory(namespace, device_rows, sensor_rows, *, now):
    """PUT /v1/hub/inventory devices from the Pi app's own lists (decision 0019, sections 1-2).

    Air conditioners keep their Pi registration id (the control heartbeat id); sensors get
    device_ref(). Every value already meets the server's rules, so one odd record never makes the
    whole list fail. Air conditioners come first, then sensors in API order: 50 and 32 KiB at most.
    """
    if not isinstance(device_rows, list) or not isinstance(sensor_rows, list):
        # A partial list would replace (and so remove) the other half on the server.
        raise ValueError('Unexpected Pi app list')
    controllable = {device['id'] for device in control_devices(device_rows)}
    devices, seen = [], set()

    def add(ident, name, room, kind, capabilities, state, reported_at, can_control):
        seen.add(ident)
        devices.append({'id': ident, 'name': name, 'room': room, 'type': kind,
                        'capabilities': list(capabilities), 'state': state,
                        'reported_at': reported_at, 'controllable': can_control})

    for row in device_rows:
        if (not isinstance(row, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(row.get('id', '')))
                or not isinstance(row.get('profile_id'), str)
                or not row['profile_id'].startswith('air_conditioner/') or row['id'] in seen):
            continue
        binding = row.get('zigbee_binding')
        private = (binding.get('friendly_name'),) if isinstance(binding, dict) else ()
        desired = row.get('last_desired_state')
        state = {}
        if isinstance(desired, dict):
            # The Pi app infers this from the last IR command; the unit sends no feedback.
            if isinstance(desired.get('power'), bool):
                state['power'] = desired['power']
            for source, target in (('mode', 'mode'), ('temperature_c', 'setpoint_c'),
                                   ('fan', 'fan')):
                value = (clean_number(desired.get(source), -100, 200) if target == 'setpoint_c'
                         else clean_text(desired.get(source), 40) or None)
                if value is not None:
                    state[target] = value
            if state:
                state['inferred'] = True
        command = row.get('last_command')
        add(row['id'], clean_label(row.get('name'), 80, private) or '에어컨',
            clean_label(row.get('room'), 40, private), 'air_conditioner', AIRCON_CAPABILITIES,
            state,
            reported_epoch(command.get('recorded_at') if isinstance(command, dict) else None, now),
            row['id'] in controllable)
    for row in sensor_rows:
        if not isinstance(row, dict) or row.get('kind') not in SENSOR_TYPES:
            continue  # other kinds wait for their own blocks
        raw = row.get('device_id')
        if not isinstance(raw, str) or not raw or device_ref(namespace, raw) in seen:
            continue
        kind, capabilities, fallback = SENSOR_TYPES[row['kind']]
        values = row.get('state') if isinstance(row.get('state'), dict) else {}
        state = {}
        if kind == 'door_sensor':
            contact = values.get('door_state')
            if contact not in ('open', 'closed') and isinstance(values.get('contact'), bool):
                contact = 'closed' if values['contact'] else 'open'
            if contact in ('open', 'closed'):
                state['contact'] = contact
        else:
            for key, low, high in (('temperature_c', -100, 200), ('humidity_percent', 0, 100)):
                value = clean_number(values.get(key), low, high)
                if value is not None:
                    state[key] = value
        battery = clean_number(values.get('battery_percent'), 0, 100)
        if battery is not None:
            state['battery_percent'] = battery
        if isinstance(values.get('battery_low'), bool):
            state['battery_low'] = values['battery_low']
        if 'battery_percent' in state or 'battery_low' in state:
            capabilities += ('battery',)
        metadata = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
        add(device_ref(namespace, raw),
            clean_label(metadata.get('display_name'), 80, (raw,)) or fallback,
            clean_label(metadata.get('room'), 40, (raw,)), kind, capabilities, state,
            reported_epoch(row.get('last_reported_at'), now), False)
    devices = devices[:INVENTORY_MAX_DEVICES]
    # Encoded exactly as ControlChannel sends it; trailing sensors give way first.
    while devices and len(json.dumps({'devices': devices}).encode()) > INVENTORY_MAX_BYTES:
        devices.pop()
    return devices


def inventory_digest(devices):
    canonical = json.dumps(devices, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


class LocalController:
    """Only reviewed profile actions; the server cannot choose a URL or arbitrary payload."""
    def __init__(self, origin):
        self.origin = control_origin(origin)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, path, value=None, timeout=15):
        request = urllib.request.Request(self.origin+path,
            data=None if value is None else json.dumps(value).encode(),
            headers={'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=timeout) as response:
            data = response.read(65537)
            if len(data) > 65536:
                raise ValueError('Controller response too large')
            return json.loads(data)

    def devices(self):
        return control_devices(self.request('/api/v1/devices')['items'])

    def inventory(self, namespace, *, clock=time.time):
        """Read-only GETs of the Pi app's device and sensor lists; nothing is sent to a unit."""
        device_rows = self.request('/api/v1/devices')['items']
        sensor_rows = self.request('/api/v1/sensors')['items']
        return build_inventory(namespace, device_rows, sensor_rows, now=clock())

    def execute(self, command):
        action = command.get('action')
        if not isinstance(action, str) or action not in CONTROL_PAYLOADS:
            return 'failed'
        payload = CONTROL_PAYLOADS[action].copy()
        try:
            # Longer than the Pi app's 18 s H2 result wait, inside the 25 s heartbeat window.
            reply = self.request('/api/v1/devices/'+command['device_id']+'/commands', payload, timeout=20)
            return 'sent' if reply.get('transmission', {}).get('status') == 'sent' else 'unknown'
        except urllib.error.HTTPError as error:
            # 4xx (e.g. 422 economy while not cooling) and 503 are refused before any IR is sent;
            # 502/500, timeouts and lost connections may follow a send and are never retried.
            return 'failed' if 400 <= error.code < 500 or error.code == 503 else 'unknown'
        except Exception:
            return 'unknown'


class ControlChannel:
    def __init__(self, config, sender):
        self.url, self.sender = endpoint(config['endpoint']), sender

    def request(self, path, body, method='POST'):
        if self.sender.blocked:
            raise RuntimeError('Hub credential rejected')
        request = urllib.request.Request(self.url+path, data=json.dumps(body).encode(), method=method,
            headers={'Authorization': 'Bearer '+self.sender.token, 'Content-Type': 'application/json',
                     'User-Agent': USER_AGENT})
        try:
            with self.sender.opener.open(request, timeout=5) as response:
                data = response.read(65537)
                if len(data)>65536:
                    raise ValueError('Control response too large')
                # A 2xx without a body (e.g. 204 for a replaced inventory) is still accepted.
                return json.loads(data) if data.strip() else {}
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                self.sender.blocked = True
            raise


LOGGED = {}


def log_limited(key, level, message, *args, every=300):
    """At most one line per key and interval: a stuck condition must not flood the bounded log."""
    now = time.monotonic()
    if now - LOGGED.get(key, -math.inf) >= every:
        LOGGED[key] = now
        LOGGER.log(level, message, *args)


class InventorySync:
    """In-memory timing of PUT /v1/hub/inventory (decision 0019, section 1).

    Sends when the canonical digest of the list changes, and an unchanged list at least every
    300 s; two attempts are never closer than 15 s. A 404 (central server without the route)
    pauses it for an hour, 429 waits Retry-After, other failures are retried later. Nothing here
    may stop the heartbeat or the command poll; only 401/403 (hub credential rejected) propagate.
    """

    def __init__(self, namespace, *, monotonic=time.monotonic, clock=time.time):
        self.namespace, self.monotonic, self.clock = namespace, monotonic, clock
        self.next_attempt = -math.inf  # no local read or central request before this
        self.sent_digest, self.sent_at = None, -math.inf
        self.missing_route_logged = False

    def sync(self, channel, controller):
        now = self.monotonic()
        if now < self.next_attempt or getattr(getattr(channel, 'sender', None), 'blocked', False):
            return 'waiting'
        self.next_attempt = now + INVENTORY_MIN_INTERVAL
        try:
            devices = controller.inventory(self.namespace, clock=self.clock)
        except Exception as error:
            kind = type(error).__name__
            log_limited('inventory-local:'+kind, logging.WARNING,
                        'INVENTORY_LOCAL_UNAVAILABLE kind=%s', kind)
            return 'local_unavailable'
        digest = inventory_digest(devices)
        if digest == self.sent_digest and now - self.sent_at < INVENTORY_REFRESH_INTERVAL:
            # The refresh is due exactly 300 s after the last send (far more than 15 s after it).
            self.next_attempt = min(self.next_attempt, self.sent_at + INVENTORY_REFRESH_INTERVAL)
            return 'unchanged'
        try:
            channel.request('/v1/hub/inventory', {'devices': devices}, 'PUT')
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise  # ControlChannel marked the hub blocked; the agent stops for inspection.
            if error.code == 404:
                self.next_attempt = now + INVENTORY_MISSING_ROUTE_WAIT
                if not self.missing_route_logged:
                    self.missing_route_logged = True
                    LOGGER.warning('INVENTORY_ROUTE_MISSING wait=%s',
                                   int(INVENTORY_MISSING_ROUTE_WAIT))
                return 'missing_route'
            if error.code == 429:
                wait = retry_after(error.headers)
                self.next_attempt = now + max(wait, INVENTORY_MIN_INTERVAL)
                log_limited('inventory-rate', logging.WARNING,
                            'INVENTORY_RATE_LIMITED wait=%s', int(wait))
                return 'rate_limited'
            rejected = 400 <= error.code < 500
            self.next_attempt = now + (INVENTORY_REJECTED_WAIT if rejected
                                       else INVENTORY_RETRY_WAIT)
            log_limited('inventory-status:'+str(error.code), logging.WARNING,
                        'INVENTORY_DEFERRED status=%s', error.code)
            return 'rejected' if rejected else 'retry'
        except Exception as error:
            # Never log the URL, authorization header, names or the provider body.
            kind = type(error).__name__
            self.next_attempt = now + INVENTORY_RETRY_WAIT
            log_limited('inventory:'+kind, logging.WARNING, 'INVENTORY_DEFERRED kind=%s', kind)
            return 'retry'
        self.sent_digest, self.sent_at = digest, now
        log_limited('inventory-sent', logging.INFO, 'INVENTORY_SENT devices=%s', len(devices))
        return 'sent'


def report_control(store, channel, receipt, state):
    """400/404/409 are definitive (unknown/re-paired/restored command): stop retrying that result."""
    try:
        channel.request('/v1/hub/control/'+receipt['id']+'/result',
                        {'attempt_token': receipt['attempt_token'], 'state': state})
    except urllib.error.HTTPError as error:
        if error.code not in (400, 404, 409):
            raise
        LOGGER.warning('AIRCON_CONTROL_RESULT_REJECTED status=%s', error.code)
    store.reported_control(receipt)


def poll_control(store, channel, controller, inventory=None, *, monotonic=time.monotonic):
    """Receipt is committed before physical send. Lost results are retried; sends never are."""
    pending = store.pending_result()
    if pending:
        # A failed retry is kept for a later poll; it must not block the heartbeat or /next.
        try:
            report_control(store, channel, pending, pending['state'])
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise
            log_limited('result', logging.WARNING, 'AIRCON_CONTROL_RESULT_DEFERRED status=%s', error.code)
        except Exception as error:
            log_limited('result', logging.WARNING, 'AIRCON_CONTROL_RESULT_DEFERRED kind=%s', type(error).__name__)
    devices = controller.devices()
    channel.request('/v1/hub/control/status', {'devices': devices}, 'PUT')
    if inventory is not None:
        # After a delivered heartbeat. Its own failures are logged and retried later; only a
        # rejected hub credential (401/403) leaves here, like every other channel request.
        inventory.sync(channel, controller)
    started = monotonic()
    command = channel.request('/v1/hub/control/next', {})['command']
    if command is None:
        return
    if (not isinstance(command, dict)
            or not re.fullmatch(r'[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}', str(command.get('id', '')))
            or not re.fullmatch(r'[a-f0-9]{32}', str(command.get('device_id', '')))
            or not re.fullmatch(r'[a-f0-9]{64}', str(command.get('attempt_token', '')))):
        raise ValueError('Invalid control command')
    if not store.begin_control(command):
        return
    # Every path below reaches finish_control, so a receipt is never left 'executing'.
    state = 'failed'
    try:
        remaining = command.get('remaining_seconds')
        # A newer server's action, a device not advertised just now or a bad window: report, never
        # send. `not remaining <= 30` also rejects NaN, inf and huge ints without raising.
        if (not isinstance(command.get('action'), str) or command['action'] not in CONTROL_PAYLOADS
                or command['device_id'] not in {device['id'] for device in devices}
                or type(remaining) not in (int, float) or not remaining <= 30):
            state = 'failed'
        elif remaining <= 0 or monotonic()-started >= remaining:
            state = 'expired'
        else:
            state = 'unknown'  # From here an error may follow a physical send; it is never retried.
            state = controller.execute(command)
    except Exception as error:
        LOGGER.warning('AIRCON_CONTROL_ERROR kind=%s', type(error).__name__)
    store.finish_control(command, state)
    LOGGER.info('AIRCON_CONTROL outcome=%s', state)
    try:
        # Result delivery can be repeated safely after a transient network failure.
        report_control(store, channel, command, state)
    finally:
        # A slow local send (up to 20 s) must not let the 25 s heartbeat lapse, even when the
        # result is deferred. Its own failure must not hide the result error (401/403 still stop).
        try:
            channel.request('/v1/hub/control/status', {'devices': devices}, 'PUT')
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise
        except Exception:
            pass


def dispatch(store, sender):
    if sender.blocked:
        return False
    item = store.next()
    if item is None:
        return False
    outcome = sender.send(item)
    store.finish(item, outcome, wait=sender.rate_limit_wait)
    if outcome == "rate_limited":
        LOGGER.warning("CENTRAL_RELAY outcome=rate_limited wait=%s", int(sender.rate_limit_wait))
    else:
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
            controller = LocalController(config['control_origin']) if config.get('control_origin') else None
            channel = ControlChannel(config, sender) if controller else None
            inventory = InventorySync(store.namespace()) if controller else None
            if args.connection_test:
                store.connection_test()
            failures = 0
            while True:
                # Relay source health never gates control: heartbeat and commands run every loop.
                # With control enabled a source problem is logged (rate-limited) instead of stopping.
                try:
                    counts = store.collect(config["source_data_dir"])
                    if any(counts.values()):
                        LOGGER.info(
                            "SOURCE_COLLECTION counts=%s", json.dumps(counts, sort_keys=True)
                        )
                    healthy = True
                except (SourceChangedError, QueueFullError):
                    # Still try to empty the queue; don't rebaseline or overwrite source history.
                    if failures % 60 == 0:
                        LOGGER.error("SOURCE_INSPECTION_REQUIRED")
                    healthy = False
                except (OSError, sqlite3.Error):
                    if failures % 60 == 0:
                        LOGGER.warning("SOURCE_TEMPORARILY_UNAVAILABLE")
                    healthy = False
                except Exception as error:
                    # e.g. a changed source schema: still stops for inspection when control is off.
                    if not controller:
                        raise
                    if failures % 60 == 0:
                        LOGGER.error("SOURCE_INSPECTION_REQUIRED kind=%s", type(error).__name__)
                    healthy = False
                try:
                    dispatch(store, sender)
                except Exception as error:
                    if not controller and not isinstance(error, (OSError, sqlite3.Error)):
                        raise
                    if failures % 60 == 0:
                        LOGGER.warning("RELAY_QUEUE_TEMPORARILY_UNAVAILABLE kind=%s", type(error).__name__)
                    healthy = False
                failures = 0 if healthy else failures + 1
                if controller:
                    try:
                        poll_control(store, channel, controller, inventory)
                    except Exception as error:
                        kind = type(error).__name__
                        log_limited('control:'+kind, logging.WARNING, 'CONTROL_TEMPORARILY_UNAVAILABLE kind=%s', kind)
                if sender.blocked:
                    LOGGER.error("HUB_AUTHENTICATION_REQUIRES_INSPECTION")
                    raise RuntimeError("Hub credential rejected")
                if args.once:
                    if failures:
                        raise RuntimeError("Source inspection failed")
                    print("AGENT_ONCE=PASS SOURCE_HISTORY_UNMODIFIED=TRUE")
                    return
                if failures >= 5 and not controller:
                    raise RuntimeError("Repeated source failure requires inspection")
                time.sleep(5)
    except Exception as error:
        LOGGER.error("AGENT_STOPPED kind=%s", type(error).__name__)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
