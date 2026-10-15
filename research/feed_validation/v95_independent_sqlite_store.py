"""Research-only SQLite persistence for independently validated Biquote BID M1 candles.

No automatic connection, no primary database reads/writes, no live signal inputs.
Caller must pass a validated candle from the isolated builder and explicit DB path.
"""
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRIMARY_DB = Path("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
DEFAULT_BACKUP_DB = Path("/home/v95research/v95-backup-research/biquote_independent_m1.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS independent_m1 (
 minute_utc TEXT PRIMARY KEY,
 open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
 tick_count INTEGER NOT NULL CHECK(tick_count >= 2),
 source TEXT NOT NULL CHECK(source = 'biquote_independent_bid'),
 validated_at_utc TEXT NOT NULL
);
"""


def _guard_path(path):
    path = Path(path).expanduser().resolve()
    if path == PRIMARY_DB.resolve():
        raise ValueError("Refusing primary collector database path")
    if path.name == PRIMARY_DB.name:
        raise ValueError("Refusing database filename reserved for primary collector")
    if path.exists() and not path.is_file():
        raise ValueError("Database path is not a regular file")
    return path


def _validate(candle):
    if candle.get("research_only") is not True:
        raise ValueError("Only independently validated research candles accepted")
    minute = datetime.fromisoformat(candle["minute"])
    if minute.tzinfo is None or minute.utcoffset() != timedelta(0):
        raise ValueError("Minute must be UTC")
    if minute.second or minute.microsecond:
        raise ValueError("Minute must be aligned to M1")
    values = tuple(float(candle[k]) for k in ("open", "high", "low", "close"))
    o, h, l, c = values
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("Nonfinite or nonpositive OHLC")
    if h < max(o, c, l) or l > min(o, c, h):
        raise ValueError("Invalid OHLC range")
    ticks = candle["ticks"]
    if isinstance(ticks, bool) or not isinstance(ticks, int) or ticks < 2:
        raise ValueError("Invalid tick count")
    return minute.astimezone(timezone.utc).isoformat(), values, ticks


def persist_validated_candle(path, candle):
    """Insert once; exact repeats are idempotent; conflicting repeats fail closed."""
    path = _guard_path(path)
    minute, (o, h, l, c), ticks = _validate(candle)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path, timeout=5) as db:
        db.execute("PRAGMA busy_timeout=5000")
        db.execute(SCHEMA)
        existing = db.execute(
            "SELECT open, high, low, close, tick_count, source FROM independent_m1 WHERE minute_utc=?",
            (minute,),
        ).fetchone()
        expected = (o, h, l, c, ticks, "biquote_independent_bid")
        if existing is not None:
            if existing != expected:
                raise ValueError("Conflicting independently observed candle")
            return "duplicate"
        db.execute(
            "INSERT INTO independent_m1 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (minute, o, h, l, c, ticks, "biquote_independent_bid",
             datetime.now(timezone.utc).isoformat()),
        )
    return "inserted"
