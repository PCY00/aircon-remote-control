"""Durable, installation-scoped delivery; topics never establish family authority."""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
import time

from central_server.households import APIError, Households, identifier, token_digest


def enqueue(conn, home, now, *, event=None, installation=None, user=None, expires_at=None):
    message = identifier()
    expires = min(now + 300, expires_at if expires_at is not None else now + 300)
    conn.execute(
        "INSERT INTO push_messages VALUES (?,?,?,?,?,?)",
        (message, home, event, "event" if event is not None else "test", now, expires),
    )
    if expires <= now:
        return message, 0
    query = (
        "SELECT i.id,i.binding,i.user_id FROM installations i "
        "JOIN users u ON u.id=i.user_id "
        "JOIN memberships m ON m.user_id=i.user_id "
        "WHERE m.home_id=? AND m.active=1 AND u.active=1 AND i.active=1 AND i.token IS NOT NULL "
        "AND i.updated_at>?"
    )
    params = [home, now - 90 * 86400]
    if installation is not None:
        query += " AND i.id=? AND i.user_id=?"
        params += [installation, user]
    rows = conn.execute(query, params).fetchall()
    for row in rows:
        conn.execute(
            "INSERT INTO push_jobs(message_id,installation_id,binding,user_id,state,due_at) "
            "VALUES (?,?,?,?,'pending',?)",
            (message, *row, now),
        )
    return message, len(rows)


class PushStore(Households):
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
                "SELECT message_id,installation_id FROM push_jobs WHERE "
                "(state='pending' AND due_at<=?) OR (state='sending' AND lease_until<=?) "
                "ORDER BY due_at LIMIT 1",
                (now, now),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE push_jobs SET state='sending',lease_until=?,attempts=attempts+1 "
                "WHERE message_id=? AND installation_id=?",
                (now + 60, *row),
            )
            return tuple(row)

    def authorized(self, job):
        # Re-read immediately before I/O, including membership and binding rotation.
        with self.transaction(write=True) as conn:
            row = conn.execute(
                "SELECT i.token,i.binding,u.subject,p.id,p.kind,p.expires_at,p.home_id "
                "FROM push_jobs j JOIN push_messages p ON p.id=j.message_id "
                "JOIN installations i ON i.id=j.installation_id "
                "JOIN users u ON u.id=i.user_id "
                "JOIN memberships m ON m.user_id=i.user_id AND m.home_id=p.home_id "
                "WHERE j.message_id=? AND j.installation_id=? AND j.state='sending' "
                "AND i.active=1 AND u.active=1 AND m.active=1 "
                "AND j.binding=i.binding AND j.user_id=i.user_id AND p.expires_at>?",
                (*job, self.clock()),
            ).fetchone()
            if not row:
                conn.execute(
                    "UPDATE push_jobs SET state='cancelled',last_error='authority_changed' "
                    "WHERE message_id=? AND installation_id=?",
                    job,
                )
            return dict(row) if row else None

    def finish(self, job, result, *, retry_after=0):
        now = self.clock()
        with self.transaction(write=True) as conn:
            row = conn.execute(
                "SELECT attempts,binding FROM push_jobs WHERE message_id=? AND installation_id=?",
                job,
            ).fetchone()
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
        # Keep bounded diagnostics. Never delete household/event records.
        with self.transaction(write=True) as conn:
            cutoff = self.clock() - 14 * 86400
            conn.execute(
                "UPDATE installations SET active=0,token=NULL WHERE active=1 AND updated_at<?",
                (self.clock() - 90 * 86400,),
            )
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
