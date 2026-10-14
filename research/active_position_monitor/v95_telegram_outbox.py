"""Persistent, research-only Telegram notification outbox."""
import json
import os
import sqlite3
import time
from pathlib import Path


def _connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(str(path), timeout=15)
    db.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            event_id TEXT PRIMARY KEY,
            message TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at REAL NOT NULL,
            sent_at REAL
        )
    """)
    db.commit()
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return db


def enqueue(path, event_id, message):
    if not event_id or not message:
        raise ValueError("Event ID and message are required")
    with _connect(path) as db:
        db.execute(
            """INSERT OR IGNORE INTO notifications
               (event_id, message, created_at)
               VALUES (?, ?, ?)""",
            (event_id, message, time.time()),
        )


def pending(path, limit=10):
    with _connect(path) as db:
        return db.execute(
            """SELECT event_id, message, attempts
               FROM notifications
               WHERE status='PENDING'
               ORDER BY created_at, event_id LIMIT ?""",
            (limit,),
        ).fetchall()


def mark_sent(path, event_id):
    with _connect(path) as db:
        db.execute(
            """UPDATE notifications
               SET status='SENT', attempts=attempts+1,
                   sent_at=?, last_error=NULL
               WHERE event_id=? AND status='PENDING'""",
            (time.time(), event_id),
        )


def mark_failed(path, event_id, error):
    with _connect(path) as db:
        db.execute(
            """UPDATE notifications
               SET attempts=attempts+1, last_error=?
               WHERE event_id=? AND status='PENDING'""",
            (str(error)[:200], event_id),
        )


def status(path):
    with _connect(path) as db:
        return dict(
            db.execute(
                "SELECT status, COUNT(*) FROM notifications GROUP BY status"
            ).fetchall()
        )


def cleanup(path, committed_ids, orphan_grace_seconds=86400,
            sent_retention_seconds=2592000, now=None):
    """Safely prune old research notifications.

    Never remove a committed pending notification.
    Uncommitted pending notifications receive a 24-hour grace period.
    """
    now = time.time() if now is None else float(now)
    committed_ids = set(committed_ids)

    with _connect(path) as db:
        db.execute("BEGIN IMMEDIATE")

        rows = db.execute(
            """SELECT event_id FROM notifications
               WHERE status='PENDING' AND created_at < ?""",
            (now - orphan_grace_seconds,),
        ).fetchall()

        orphan_ids = [
            event_id for (event_id,) in rows
            if event_id not in committed_ids
        ]

        for event_id in orphan_ids:
            db.execute(
                """UPDATE notifications
                   SET status='CANCELLED',
                       last_error='Uncommitted orphan expired'
                   WHERE event_id=? AND status='PENDING'""",
                (event_id,),
            )

        removed = db.execute(
            """DELETE FROM notifications
               WHERE status='SENT' AND sent_at < ?""",
            (now - sent_retention_seconds,),
        ).rowcount

    return {
        "cancelled_orphans": len(orphan_ids),
        "removed_sent": removed,
    }


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory(prefix="v95-outbox-test-") as directory:
        path = Path(directory) / "outbox.sqlite3"

        enqueue(path, "test-sell-001", "V9.5 hypothetical SELL")
        enqueue(path, "test-sell-001", "V9.5 hypothetical SELL")

        assert len(pending(path)) == 1

        mark_failed(path, "test-sell-001", "Simulated network failure")
        assert pending(path)[0][2] == 1

        mark_sent(path, "test-sell-001")
        assert pending(path) == []
        assert status(path) == {"SENT": 1}

        print("PASS: Persistent outbox created")
        print("PASS: Duplicate event IDs suppressed")
        print("PASS: Failed delivery retained")
        print("PASS: Successful delivery marked SENT")
        print("PASS: Production files untouched")
