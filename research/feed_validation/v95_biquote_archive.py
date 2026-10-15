"""Archive genuine Biquote M1 candles from the existing V9.5 SQLite store.

Research-only shadow component. Reads the primary database in SQLite read-only
mode; writes only to a separate archive. Does not repair gaps or alter trades.
Run periodically from an approved, restricted Oracle service after validation.
"""
import argparse
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path

DEFAULT_SOURCE = Path.home() / "v95-detector-dev/research/feed_validation/biquote_m1.sqlite3"
DEFAULT_ARCHIVE = Path.home() / "v95-candle-recovery/archive/biquote_m1_archive.sqlite3"
UTC = dt.timezone.utc


def validate(row):
    minute, o, h, l, c, ticks = row
    stamp = dt.datetime.fromisoformat(minute.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0):
        raise ValueError("Non-UTC candle minute")
    if stamp.second or stamp.microsecond:
        raise ValueError("Non-aligned candle minute")
    values = tuple(float(x) for x in (o, h, l, c))
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("Invalid OHLC")
    if not values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1]:
        raise ValueError("Invalid OHLC ordering")
    if int(ticks) < 2:
        raise ValueError("Insufficient genuine tick count")
    return (stamp.astimezone(UTC).isoformat(), *values, int(ticks))


def archive(source, destination, limit=5000):
    if not 1 <= limit <= 100000:
        raise ValueError("limit outside 1..100000")
    if source.resolve() == destination.resolve():
        raise ValueError("Archive cannot equal primary database")
    # Fail closed if the source database does not exist.
    with sqlite3.connect("file:" + str(source.resolve()) + "?mode=ro", uri=True) as primary:
        rows = primary.execute(
            "SELECT minute, open, high, low, close, ticks "
            "FROM candles ORDER BY minute DESC LIMIT ?", (limit,)
        ).fetchall()
    verified = [validate(row) for row in rows]
    destination.parent.mkdir(parents=True, exist_ok=True)
    inserted = 0
    conflicts = 0
    with sqlite3.connect(destination) as backup:
        backup.execute("""CREATE TABLE IF NOT EXISTS archived_candles (
            minute TEXT PRIMARY KEY, open REAL NOT NULL, high REAL NOT NULL,
            low REAL NOT NULL, close REAL NOT NULL, ticks INTEGER NOT NULL,
            provenance TEXT NOT NULL CHECK (provenance = 'biquote_primary_verified')
        )""")
        for row in reversed(verified):
            previous = backup.execute(
                "SELECT open,high,low,close,ticks FROM archived_candles WHERE minute=?",
                (row[0],)
            ).fetchone()
            if previous is not None:
                if tuple(previous) != tuple(row[1:]):
                    conflicts += 1
                continue
            backup.execute(
                "INSERT INTO archived_candles VALUES (?,?,?,?,?,?,?)",
                (*row, "biquote_primary_verified")
            )
            inserted += 1
    return {"mode": "ARCHIVE_ONLY", "source_rows": len(rows),
            "inserted": inserted, "conflicts": conflicts,
            "archive": str(destination), "primary_modified": False,
            "note": "An archive of primary candles cannot recover minutes the primary never captured."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()
    try:
        result = archive(args.source, args.archive, args.limit)
        print(json.dumps(result, sort_keys=True))
        if result["conflicts"]:
            raise SystemExit(2)
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
