"""V9.5 research-only candle gap audit. Read-only; no provider requests or trading.

This tool identifies absent UTC M1 slots in the *observed* candle range.
A gap is not assumed recoverable, and no synthetic candles are produced.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
DEFAULT_DB = Path.home() / "v95-detector-dev/research/feed_validation/biquote_m1.sqlite3"


def trading_minute(moment):
    """Standard XAU/USD session assumption; holidays/provider closures excluded."""
    local = moment.astimezone(NY)
    day, hour = local.weekday(), local.hour
    if day == 5 or (day == 4 and hour >= 17) or (day == 6 and hour < 17):
        return False
    if day < 4 and hour == 17:
        return False
    return True


def parse_minute(value):
    moment = dt.datetime.fromisoformat(value)
    if moment.tzinfo is None or moment.utcoffset() != dt.timedelta(0):
        raise ValueError("Candle timestamp must be UTC-aware")
    if moment.second or moment.microsecond:
        raise ValueError("Candle timestamp must align to a minute")
    return moment.astimezone(UTC)


def inspect(path, limit=2500):
    if limit < 2 or limit > 100000:
        raise ValueError("limit must be between 2 and 100000")
    # SQLite URI read-only prevents accidentally creating a new DB.
    with sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True) as db:
        records = db.execute(
            "SELECT minute FROM candles ORDER BY minute DESC LIMIT ?", (limit,)
        ).fetchall()
    moments = sorted(parse_minute(record[0]) for record in records)
    if len(moments) < 2:
        return {"observed_candles": len(moments), "missing": [], "count": 0}
    if len(set(moments)) != len(moments):
        raise ValueError("Duplicate UTC candle minutes")
    missing = []
    for previous, current in zip(moments, moments[1:]):
        cursor = previous + dt.timedelta(minutes=1)
        while cursor < current:
            if trading_minute(cursor):
                missing.append(cursor.isoformat())
            cursor += dt.timedelta(minutes=1)
    return {
        "observed_candles": len(moments),
        "first": moments[0].isoformat(),
        "last": moments[-1].isoformat(),
        "count": len(missing),
        "missing": missing,
        "mode": "READ_ONLY_AUDIT",
        "note": "Holiday/provider closures need separate verification; no backfill attempted.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=2500)
    args = parser.parse_args()
    print(json.dumps(inspect(args.db, args.limit), indent=2))


if __name__ == "__main__":
    main()
