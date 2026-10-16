"""Staging-only Twelve Data M1 recovery into an isolated SQLite cache.

Never modifies Biquote databases, V9.4 LIVE, or running V9.5 PAPER.
Only completed genuine provider M1 candles are stored. A contiguous window
from this single source can later be evaluated in an explicitly approved
paper-only integration; do not splice providers.
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

UTC = dt.timezone.utc
DEFAULT_CACHE = Path("/home/ubuntu/v95-recovery-staging/twelve_m1_cache.sqlite3")


def parse_values(payload, now):
    if payload.get("status") == "error" or not isinstance(payload.get("values"), list):
        raise ValueError("provider returned no historical M1 values")
    rows = []
    for item in payload["values"]:
        stamp = dt.datetime.fromisoformat(item["datetime"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        stamp = stamp.astimezone(UTC)
        if stamp.second or stamp.microsecond or stamp + dt.timedelta(minutes=1) > now:
            continue
        vals = [float(item[k]) for k in ("open", "high", "low", "close")]
        o, h, l, c = vals
        if not all(math.isfinite(x) and x > 0 for x in vals) or not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("invalid provider OHLC")
        rows.append((stamp.isoformat(), o, h, l, c))
    rows.sort()
    if len({r[0] for r in rows}) != len(rows):
        raise ValueError("duplicate provider minute")
    return rows


def fetch(api_key, outputsize=600):
    if not api_key:
        raise ValueError("TWELVE_DATA_API_KEY is missing")
    params = urlencode({"symbol": "XAU/USD", "interval": "1min",
                        "outputsize": outputsize, "timezone": "UTC",
                        "apikey": api_key})
    # Never print URLs: they contain API keys.
    with urlopen("https://api.twelvedata.com/time_series?" + params, timeout=25) as response:
        return json.load(response)


def store(cache, rows):
    cache.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(cache) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS twelve_m1 (
            minute_utc TEXT PRIMARY KEY, open REAL NOT NULL, high REAL NOT NULL,
            low REAL NOT NULL, close REAL NOT NULL)""")
        db.executemany("INSERT OR IGNORE INTO twelve_m1 VALUES (?,?,?,?,?)", rows)
        count = db.execute("SELECT count(*) FROM twelve_m1").fetchone()[0]
    return count


def continuity(cache, now, lookback=270):
    with sqlite3.connect(f"file:{cache.resolve()}?mode=ro", uri=True) as db:
        present = {dt.datetime.fromisoformat(x[0]) for x in db.execute(
            "SELECT minute_utc FROM twelve_m1 ORDER BY minute_utc DESC LIMIT 3000")}
    latest_closed = now.replace(second=0, microsecond=0) - dt.timedelta(minutes=1)
    # Latest candle may not have been published yet; report that fact, don't hide it.
    missing = [latest_closed - dt.timedelta(minutes=i)
               for i in range(lookback)
               if latest_closed - dt.timedelta(minutes=i) not in present]
    return {"source": "TWELVE_DATA_ONLY", "latest_expected_utc": latest_closed.isoformat(),
            "missing_count": len(missing), "missing_utc": [x.isoformat() for x in reversed(missing)],
            "entry_authorized": False, "biquote_modified": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    p.add_argument("--outputsize", type=int, default=600)
    p.add_argument("--lookback", type=int, default=270)
    p.add_argument("--offline-json", type=Path)
    args = p.parse_args()
    if not 1 <= args.outputsize <= 5000 or not 1 <= args.lookback <= 2700:
        p.error("invalid outputsize or lookback")
    now = dt.datetime.now(UTC)
    if args.offline_json:
        payload = json.loads(args.offline_json.read_text())
    else:
        payload = fetch(os.getenv("TWELVE_DATA_API_KEY", ""), args.outputsize)
    rows = parse_values(payload, now)
    if not rows:
        raise ValueError("no completed M1 candles in response")
    count = store(args.cache, rows)
    report = continuity(args.cache, now, args.lookback)
    report.update({"fetched_completed": len(rows), "cached_total": count})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
