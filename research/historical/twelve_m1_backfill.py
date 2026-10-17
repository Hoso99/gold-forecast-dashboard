#!/usr/bin/env python3
"""Isolated Twelve Data XAU/USD M1 historical archive. DRY RUN by default.

Example first authorized bounded test:
 python3 research/historical/twelve_m1_backfill.py --execute --max-requests 1
Never run as a live or paper trading component.
"""
import argparse
import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

FMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_DB = "/home/ubuntu/v95-historical-research/twelve_xauusd_m1.sqlite3"
DEFAULT_ENV = "/home/ubuntu/.config/v95-research/monitor.env"

def dt(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

def load_key(path):
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("TWELVE_DATA_API_KEY="):
            return line.partition("=")[2].strip().strip('"').strip("'")
    raise RuntimeError("API key not configured")

def fetch(key, start, end):
    query = urlencode({
        "symbol": "XAU/USD", "interval": "1min",
        "start_date": start.strftime(FMT),
        "end_date": (end - timedelta(minutes=1)).strftime(FMT),
        "outputsize": 5000, "timezone": "UTC", "apikey": key,
    })
    with urlopen("https://api.twelvedata.com/time_series?" + query, timeout=90) as resp:
        payload = json.load(resp)
    if not isinstance(payload.get("values"), list):
        raise RuntimeError("API error: " + str(payload.get("message", "missing candles")))
    return payload["values"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-04-06T16:40:00")
    parser.add_argument("--end", default="2020-04-10T00:00:00")
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--env", default=DEFAULT_ENV)
    parser.add_argument("--window-minutes", type=int, default=4500)
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    start, end = dt(args.start), dt(args.end)
    if not start < end or start.second or end.second:
        parser.error("invalid minute-aligned UTC range")
    if not 1 <= args.window_minutes <= 4500 or not 1 <= args.max_requests <= 100:
        parser.error("invalid limits")
    print("MODE:", "EXECUTE" if args.execute else "DRY RUN")
    print("RANGE UTC:", start, end, "(end exclusive)")
    print("DB:", args.db)
    print("MAX REQUESTS:", args.max_requests)
    if not args.execute:
        return
    db = Path(args.db)
    if db.exists() and not db.is_file():
        raise RuntimeError("database path is not a file")
    db.parent.mkdir(parents=True, exist_ok=True)
    key = load_key(args.env)
    if not key:
        raise RuntimeError("empty API key")
    con = sqlite3.connect(str(db))
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS candles (
            minute_utc TEXT PRIMARY KEY, open REAL, high REAL, low REAL, close REAL)""")
        con.execute("""CREATE TABLE IF NOT EXISTS completed_windows (
            start_utc TEXT, end_utc TEXT, rows_received INTEGER,
            PRIMARY KEY (start_utc, end_utc))""")
        con.commit()
        cursor = start
        requests = 0
        while cursor < end:
            stop = min(cursor + timedelta(minutes=args.window_minutes), end)
            a, b = cursor.strftime(FMT), stop.strftime(FMT)
            if con.execute("SELECT 1 FROM completed_windows WHERE start_utc=? AND end_utc=?", (a,b)).fetchone():
                print("SKIP:", a, b)
                cursor = stop
                continue
            if requests >= args.max_requests:
                print("STOP: request limit")
                break
            values = fetch(key, cursor, stop)
            requests += 1
            if len(values) >= 5000:
                raise RuntimeError("5000-row cap reached: shorten window")
            rows, seen = [], set()
            for v in values:
                stamp = dt(v["datetime"])
                if not cursor <= stamp < stop or stamp.second or stamp.microsecond:
                    raise RuntimeError("out-of-window timestamp")
                if stamp in seen:
                    raise RuntimeError("duplicate timestamp")
                seen.add(stamp)
                o,h,l,c = [float(v[k]) for k in ("open","high","low","close")]
                if not all(map(math.isfinite, (o,h,l,c))) or not l <= min(o,c) <= max(o,c) <= h:
                    raise RuntimeError("invalid OHLC")
                rows.append((stamp.strftime(FMT),o,h,l,c))
            with con:
                con.executemany("INSERT OR IGNORE INTO candles VALUES (?,?,?,?,?)", rows)
                con.execute("INSERT INTO completed_windows VALUES (?,?,?)", (a,b,len(rows)))
            print("SAVED:", len(rows), "range:", a, b)
            cursor = stop
        print("TOTAL CANDLES:", con.execute("SELECT COUNT(*) FROM candles").fetchone()[0])
    finally:
        con.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("STOPPED:", type(exc).__name__, str(exc), file=sys.stderr)
        sys.exit(1)
