"""Read-only V9.5 gap audit and authenticated-candle recovery planner.

Never invent candles, change risk rules, or write to a running collector database.
A recovery source must return genuine M1 OHLC on the same Biquote price basis.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

UTC = dt.timezone.utc
PRIMARY = Path("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
SECONDARY = Path("/home/v95research/v95-backup-research/biquote_independent_m1.sqlite3")


def read_minutes(path, table, column, limit=3000):
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        return {
            dt.datetime.fromisoformat(row[0]).astimezone(UTC)
            for row in db.execute(
                f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT ?", (limit,)
            )
        }


def audit(primary, secondary=None, lookback=270):
    main = read_minutes(primary, "candles", "minute")
    if not main:
        raise ValueError("primary has no M1 candles")
    latest = max(main)
    start = latest - dt.timedelta(minutes=lookback - 1)
    gaps = [start + dt.timedelta(minutes=i) for i in range(lookback)
            if start + dt.timedelta(minutes=i) not in main]
    report = {
        "latest_utc": latest.isoformat(),
        "missing_count": len(gaps),
        "missing_utc": [t.isoformat() for t in gaps],
        "recoverable_from_secondary_utc": [],
        "unrecoverable_without_historical_source_utc": [],
        "writes_performed": False,
        "entry_gate_bypassed": False,
    }
    other = None
    if secondary is not None:
        try:
            other = read_minutes(secondary, "independent_m1", "minute_utc")
        except (OSError, sqlite3.Error) as exc:
            report["secondary_status"] = "unavailable: " + type(exc).__name__
    else:
        report["secondary_status"] = "not configured"
    if other is not None:
        report["secondary_status"] = "readable"
        report["recoverable_from_secondary_utc"] = [
            t.isoformat() for t in gaps if t in other
        ]
        report["unrecoverable_without_historical_source_utc"] = [
            t.isoformat() for t in gaps if t not in other
        ]
    else:
        report["unrecoverable_without_historical_source_utc"] = report["missing_utc"]
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, default=PRIMARY)
    parser.add_argument("--secondary", type=Path, default=SECONDARY)
    parser.add_argument("--lookback", type=int, default=270)
    args = parser.parse_args()
    if not 1 <= args.lookback <= 3000:
        parser.error("--lookback must be 1..3000")
    print(json.dumps(audit(args.primary, args.secondary, args.lookback), indent=2))


if __name__ == "__main__":
    main()
