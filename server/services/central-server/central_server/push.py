"""Durable, installation-scoped delivery; topics never establish family authority."""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
import time

from central_server.households import APIError, Households, identifier, token_digest
from central_server.preferences import (
    LEGACY,
    PUSHED,
    alert_category,
    category,
    level,
    levels,
    read,
)

INSTALLATION_ROWS_PER_USER = 50
PENDING_JOBS_PER_HOME = 500


def discard_installations(conn, ids):
    for installation in ids:
        conn.execute("DELETE FROM notification_levels WHERE installation_id=?", (installation,))
        conn.execute("DELETE FROM notification_preferences WHERE installation_id=?", (installation,))
        conn.execute("DELETE FROM push_jobs WHERE installation_id=?", (installation,))
        conn.execute("DELETE FROM installations WHERE id=?", (installation,))


def enqueue(conn, home, now, *, event=None, installation=None, user=None, expires_at=None):
    message = identifier()
    expires = min(now + 300, expires_at if expires_at is not None else now + 300)
    conn.execute(
        "INSERT INTO push_messages VALUES (?,?,?,?,?,?)",
        (message, home, event, "event" if event is not None else "test", now, expires),
    )
    if expires <= now:
        return message, 0
    event_kind = (
        conn.execute("SELECT kind FROM events WHERE id=?", (event,)).fetchone()
        if event is not None
        else None
    )
    selected = alert_category(event_kind["kind"] if event_kind else None)
    query = (
        "SELECT i.id,i.binding,i.user_id FROM installations i "
        "JOIN users u ON u.id=i.user_id "
        "JOIN memberships m ON m.user_id=i.user_id "
        "JOIN homes h ON h.id=m.home_id "
        "WHERE m.home_id=? AND m.active=1 AND u.active=1 AND i.active=1 AND i.token IS NOT NULL "
        "AND h.active=1 AND i.updated_at>?"
    )
    params = [home, now - 90 * 86400]
    if installation is not None:
        query += " AND i.id=? AND i.user_id=?"
        params += [installation, user]
    rows = conn.execute(query, params).fetchall()
    queued = 0
    for row in rows:
        if level(conn, row["id"], row["user_id"], selected) not in PUSHED:
            continue  # quiet and off stay in the home's history only
        if selected == "report":
            preference = conn.execute(
                "SELECT * FROM notification_preferences WHERE installation_id=? AND user_id=?",
                (row["id"], row["user_id"]),
            ).fetchone()
            if (
                preference
                and preference["last_climate_at"] > 0
                and now
                < preference["last_climate_at"] + preference["climate_interval_minutes"] * 60
            ):
                continue
            conn.execute(
                "UPDATE notification_preferences SET last_climate_at=? "
                "WHERE installation_id=? AND user_id=?",
                (now, row["id"], row["user_id"]),
            )
        conn.execute(
            "INSERT INTO push_jobs(message_id,installation_id,binding,user_id,state,due_at) "
            "VALUES (?,?,?,?,'pending',?)",
            (message, *row, now),
        )
        queued += 1
    if queued:
        # Bound unsent work per home: the oldest pending jobs make room for the newest.
        excess = conn.execute(
            "SELECT j.message_id,j.installation_id FROM push_jobs j "
            "JOIN push_messages p ON p.id=j.message_id WHERE p.home_id=? AND j.state='pending' "
            "ORDER BY p.created_at DESC,j.rowid DESC LIMIT -1 OFFSET ?",
            (home, PENDING_JOBS_PER_HOME),
        ).fetchall()
        for job in excess:
            conn.execute(
                "DELETE FROM push_jobs WHERE message_id=? AND installation_id=?", tuple(job)
            )
        if excess:
            logging.warning("PUSH_QUEUE_CAPPED dropped=%d", len(excess))  # no home or device ids
    return message, queued


class PushStore(Households):
    @staticmethod
    def proven(conn, user, installation, secret):
        row = conn.execute(
            "SELECT * FROM installations WHERE id=? AND user_id=? AND active=1",
            (installation, user),
        ).fetchone()
        if not row or not secrets.compare_digest(
            row["secret_digest"], token_digest("installation", secret)
        ):
            raise APIError("not_found", 404)

    @staticmethod
    def save_switches(conn, installation, user, door, climate, warning, interval):
        conn.execute(
            "INSERT INTO notification_preferences(installation_id,user_id,door,climate,"
            "warning,climate_interval_minutes) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(installation_id) DO UPDATE SET "
            "last_climate_at=CASE WHEN notification_preferences.user_id=excluded.user_id "
            "THEN notification_preferences.last_climate_at ELSE 0 END,"
            "user_id=excluded.user_id,door=excluded.door,climate=excluded.climate,warning=excluded.warning,"
            "climate_interval_minutes=excluded.climate_interval_minutes",
            (installation, user, int(door), int(climate), int(warning), interval),
        )

    @staticmethod
    def save_levels(conn, installation, user, chosen):
        # A previous account's rows on this phone must not mix with the current account's choices.
        conn.execute(
            "DELETE FROM notification_levels WHERE installation_id=? AND user_id!=?",
            (installation, user),
        )
        for name, value in chosen.items():
            conn.execute(
                "INSERT INTO notification_levels VALUES (?,?,?,?) "
                "ON CONFLICT(installation_id,category) DO UPDATE SET "
                "user_id=excluded.user_id,level=excluded.level",
                (installation, user, name, value),
            )

    def set_preferences(self, user, installation, secret, options):
        with self.transaction(write=True) as conn:
            self.proven(conn, user, installation, secret)
            self.save_switches(
                conn,
                installation,
                user,
                options["door"],
                options["climate"],
                options["warning"],
                options["climate_interval_minutes"],
            )
            # Old app builds always send all three switches: a switch keeps a level of the same
            # meaning (on: urgent/alert, off: quiet/off) so one toggle cannot rewrite the others.
            current = levels(conn, installation, user)
            self.save_levels(
                conn,
                installation,
                user,
                {
                    name: current[name]
                    if (current[name] in PUSHED) == options[switch]
                    else ("alert" if options[switch] else "off")
                    for switch, name in LEGACY.items()
                },
            )
            return {"status": "saved", "preferences": read(conn, installation, user)}

    def set_levels(self, user, installation, secret, chosen, interval):
        with self.transaction(write=True) as conn:
            self.proven(conn, user, installation, secret)
            self.save_levels(conn, installation, user, chosen)
            # Keep the legacy switches meaning the same for old builds reading them back.
            self.save_switches(
                conn,
                installation,
                user,
                *(chosen[LEGACY[switch]] in PUSHED for switch in ("door", "climate", "warning")),
                interval,
            )
            return {
                "status": "saved",
                "levels": levels(conn, installation, user),
                "report_interval_minutes": interval,
            }

    def register(self, user, installation, secret, token):
        digest = token_digest("installation", secret)
        with self.transaction(write=True) as conn:
            if not conn.execute("SELECT 1 FROM users WHERE id=? AND active=1", (user,)).fetchone():
                raise APIError("account_disabled", 403)
            old = conn.execute("SELECT * FROM installations WHERE id=?", (installation,)).fetchone()
            if old and not secrets.compare_digest(old["secret_digest"], digest):
                raise APIError("installation_conflict", 409)
            if (not old or old["user_id"] != user or not old["active"]) and conn.execute(
                "SELECT COUNT(*) FROM installations WHERE user_id=? AND active=1", (user,)
            ).fetchone()[0] >= 10:
                raise APIError("installation_limit", 409)
            if not old:
                # Bound rows per account: signed-out registrations make room for a new phone.
                total = conn.execute(
                    "SELECT COUNT(*) FROM installations WHERE user_id=?", (user,)
                ).fetchone()[0]
                if total >= INSTALLATION_ROWS_PER_USER:
                    stale = conn.execute(
                        "SELECT id FROM installations WHERE user_id=? AND active=0 "
                        "ORDER BY updated_at LIMIT ?",
                        (user, total - INSTALLATION_ROWS_PER_USER + 1),
                    ).fetchall()
                    discard_installations(conn, [row["id"] for row in stale])
                    if total - len(stale) >= INSTALLATION_ROWS_PER_USER:
                        raise APIError("quota_exceeded", 429)
            # A token moves here only from the same account, a signed-out row or a holder silent
            # for 30 days; a stranger's registration cannot silence a live phone's notifications.
            holder = conn.execute(
                "SELECT user_id,active,updated_at FROM installations WHERE token=? AND id!=?",
                (token, installation),
            ).fetchone()
            if (holder and holder["user_id"] != user and holder["active"]
                    and holder["updated_at"] >= self.clock() - 30 * 86400):
                raise APIError("installation_conflict", 409)
            conn.execute(
                "UPDATE installations SET token=NULL,active=0,binding=?,updated_at=? "
                "WHERE token=? AND id!=?",
                (identifier(), self.clock(), token, installation),
            )
            binding = (
                old["binding"]
                if old and old["user_id"] == user and old["token"] == token and old["active"]
                else identifier()
            )
            try:
                conn.execute(
                    "INSERT INTO installations VALUES (?,?,?,?,?,1,?) "
                    "ON CONFLICT(id) DO UPDATE SET user_id=excluded.user_id,token=excluded.token,"
                    "binding=excluded.binding,active=1,updated_at=excluded.updated_at",
                    (installation, digest, user, token, binding, self.clock()),
                )
            except sqlite3.IntegrityError as error:
                raise APIError("installation_conflict", 409) from error
            return {"binding": binding, "status": "registered"}

    def unregister(self, user, installation, secret, binding):
        with self.transaction(write=True) as conn:
            row = conn.execute("SELECT * FROM installations WHERE id=?", (installation,)).fetchone()
            if (
                not row
                or row["user_id"] != user
                or not secrets.compare_digest(
                    row["secret_digest"], token_digest("installation", secret)
                )
            ):
                raise APIError("not_found", 404)
            if row["binding"] != binding:
                return {"status": "stale_binding_ignored"}
            conn.execute(
                "UPDATE installations SET active=0,token=NULL,binding=?,updated_at=? WHERE id=?",
                (identifier(), self.clock(), installation),
            )
            return {"status": "unregistered"}

    def test(self, home, user, installation):
        with self.transaction(write=True) as conn:
            self.access(conn, home, user, owner=True)
            if not conn.execute(
                "SELECT 1 FROM installations WHERE id=? AND user_id=? AND active=1",
                (installation, user),
            ).fetchone():
                raise APIError("installation_not_registered", 409)
            if conn.execute(
                "SELECT 1 FROM push_messages WHERE home_id=? AND kind='test' AND created_at>?",
                (home, self.clock() - 60),
            ).fetchone():
                raise APIError("test_rate_limited", 429)
            message, count = enqueue(conn, home, self.clock(), installation=installation, user=user)
            return {"message_id": message, "queued": count, "status": "queued"}

    last_home = None  # the home served by the previous claim yields to every other home

    def claim(self):
        now = self.clock()
        with self.transaction(write=True) as conn:
            conn.execute(
                "UPDATE push_jobs SET state='cancelled',last_error='expired' "
                "WHERE state IN ('pending','sending') "
                "AND message_id IN (SELECT id FROM push_messages WHERE expires_at<=?)",
                (now,),
            )
            row = conn.execute(
                "SELECT j.message_id,j.installation_id,p.home_id FROM push_jobs j "
                "JOIN push_messages p ON p.id=j.message_id WHERE "
                "(j.state='pending' AND j.due_at<=?) OR (j.state='sending' AND j.lease_until<=?) "
                "ORDER BY p.home_id=?,j.due_at LIMIT 1",
                (now, now, self.last_home or ""),
            ).fetchone()
            if not row:
                return None
            self.last_home = row["home_id"]
            conn.execute(
                "UPDATE push_jobs SET state='sending',lease_until=?,attempts=attempts+1 "
                "WHERE message_id=? AND installation_id=?",
                (now + 60, row[0], row[1]),
            )
            return (row[0], row[1])

    def authorized(self, job):
        # Re-read immediately before I/O, including membership and binding rotation.
        with self.transaction(write=True) as conn:
            row = conn.execute(
                "SELECT i.token,i.binding,i.user_id,u.subject,p.id,p.kind,p.expires_at,"
                "p.home_id,e.kind AS event_kind "
                "FROM push_jobs j JOIN push_messages p ON p.id=j.message_id "
                "JOIN installations i ON i.id=j.installation_id "
                "JOIN users u ON u.id=i.user_id "
                "JOIN memberships m ON m.user_id=i.user_id AND m.home_id=p.home_id "
                "JOIN homes h ON h.id=p.home_id LEFT JOIN events e ON e.id=p.event_id "
                "WHERE j.message_id=? AND j.installation_id=? AND j.state='sending' "
                "AND i.active=1 AND u.active=1 AND m.active=1 AND h.active=1 "
                "AND j.binding=i.binding AND j.user_id=i.user_id AND p.expires_at>?",
                (*job, self.clock()),
            ).fetchone()
            kind = row["event_kind"] if row else None
            selected = alert_category(kind)
            chosen = level(conn, job[1], row["user_id"], selected) if row else None
            allowed = chosen in PUSHED
            if not allowed:
                conn.execute(
                    "UPDATE push_jobs SET state='cancelled',last_error='authority_changed' "
                    "WHERE message_id=? AND installation_id=?",
                    job,
                )
            # Keep operational details off the provider payload and diagnostic recipient.
            return (
                {
                    key: row[key]
                    for key in (
                        "token",
                        "binding",
                        "subject",
                        "id",
                        "kind",
                        "expires_at",
                        "home_id",
                    )
                }
                | {"category": category(kind), "alert_category": selected, "level": chosen}
                if allowed
                else None
            )

    def finish(self, job, result, *, retry_after=0):
        now = self.clock()
        with self.transaction(write=True) as conn:
            row = conn.execute(
                "SELECT attempts,binding FROM push_jobs WHERE message_id=? AND installation_id=?",
                job,
            ).fetchone()
            if not row:
                return  # pruned with its event or installation while the send was in flight
            if result == "accepted":
                state, error, due = "accepted", None, now
            elif result == "unregistered":
                state, error, due = "failed", result, now
                # A late provider response must not disable a newly rotated token.
                conn.execute(
                    "UPDATE installations SET active=0,token=NULL WHERE id=? AND binding=?",
                    (job[1], row["binding"]),
                )
            elif result == "retry" and row["attempts"] < 6:
                state, error = "pending", "temporary_provider_failure"
                due = now + max(2 ** row["attempts"] * 5, min(retry_after, 300))
            else:
                state, error, due = "failed", "provider_rejected", now
            conn.execute(
                "UPDATE push_jobs SET state=?,last_error=?,due_at=?,lease_until=0 "
                "WHERE message_id=? AND installation_id=?",
                (state, error, due, *job),
            )

    def prune(self):
        # Keep bounded diagnostics. Never delete household records; events are capped per home.
        with self.transaction(write=True) as conn:
            cutoff = self.clock() - 14 * 86400
            conn.execute(
                "UPDATE installations SET active=0,token=NULL WHERE active=1 AND updated_at<?",
                (self.clock() - 90 * 86400,),
            )
            stale = conn.execute(
                "SELECT id FROM installations WHERE active=0 AND updated_at<?",
                (self.clock() - 30 * 86400,),
            ).fetchall()
            discard_installations(conn, [row["id"] for row in stale])
            conn.execute("DELETE FROM invitations WHERE expires_at<?", (self.clock() - 30 * 86400,))
            conn.execute(
                "DELETE FROM push_jobs WHERE message_id IN "
                "(SELECT id FROM push_messages WHERE expires_at<?)",
                (cutoff,),
            )
            conn.execute("DELETE FROM push_messages WHERE expires_at<?", (cutoff,))


class PushWorker:
    def __init__(self, store, sender):
        self.store, self.sender = store, sender
        self.stopped = threading.Event()

    def once(self):
        job = self.store.claim()
        if job is None:
            return False
        recipient = self.store.authorized(job)
        if recipient:
            result, wait = self.sender.send(recipient)
            self.store.finish(job, result, retry_after=wait)
            logging.info("PUSH_DISPATCH outcome=%s", result)  # no token, IDs or provider response
        return True

    def run(self):
        next_prune = 0
        while not self.stopped.is_set():
            try:
                if time.monotonic() >= next_prune:
                    self.store.prune()
                    next_prune = time.monotonic() + 3600
                if self.once():
                    continue
            except Exception as error:
                logging.warning("PUSH_WORKER_FAILED kind=%s", type(error).__name__)
            self.stopped.wait(2)

    def start(self):
        thread = threading.Thread(target=self.run, name="family-push", daemon=True)
        thread.start()
        return thread
