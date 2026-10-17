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
import time
from urllib.error import HTTPError, URLError
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

def fetch(key, start, end, retries=3):
    query = urlencode({
        "symbol": "XAU/USD", "interval": "1min",
        "start_date": start.strftime(FMT),
        "end_date": (end - timedelta(minutes=1)).strftime(FMT),
        "outputsize": 5000, "timezone": "UTC", "apikey": key,
    })
    url = "https://api.twelvedata.com/time_series?" + query
    for attempt in range(retries + 1):
        try:
            with urlopen(url, timeout=90) as resp:
                payload = json.load(resp)
            break
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == retries:
                raise RuntimeError("Twelve Data HTTP status " + str(exc.code)) from None
            wait = min(120.0, 3.0 * (2 ** attempt))
            print("RETRY HTTP", exc.code, "after", wait, "seconds", flush=True)
            time.sleep(wait)
        except (URLError, TimeoutError):
            if attempt == retries:
                raise RuntimeError("Twelve Data network error after retries") from None
            wait = min(120.0, 3.0 * (2 ** attempt))
            print("RETRY network after", wait, "seconds", flush=True)
            time.sleep(wait)
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
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--delay-seconds", type=float, default=3.0)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    start, end = dt(args.start), dt(args.end)
    if not start < end or start.second or end.second:
        parser.error("invalid minute-aligned UTC range")
    if not 1 <= args.window_minutes <= 4500 or not 1 <= args.max_requests <= 100 or not 0 <= args.retries <= 6 or not 1 <= args.delay_seconds <= 120:
        parser.error("invalid limits")
    print("MODE:", "EXECUTE" if args.execute else "DRY RUN")
    print("RANGE UTC:", start, end, "(end exclusive)")
    print("DB:", args.db)
    print("MAX REQUESTS:", args.max_requests)
    print("MINIMUM DELAY BETWEEN REQUESTS:", args.delay_seconds, "seconds")
    if args.audit_only:
        if not Path(args.db).is_file():
            raise RuntimeError("archive database does not exist")
        con = sqlite3.connect("file:" + args.db + "?mode=ro", uri=True)
        try:
            n, first, last = con.execute("SELECT COUNT(*), MIN(minute_utc), MAX(minute_utc) FROM candles").fetchone()
            w, total = con.execute("SELECT COUNT(*), COALESCE(SUM(rows_received),0) FROM completed_windows").fetchone()
            duplicates = con.execute("SELECT COUNT(*) - COUNT(DISTINCT minute_utc) FROM candles").fetchone()[0]
            invalid = con.execute("SELECT COUNT(*) FROM candles WHERE low > high OR open < low OR open > high OR close < low OR close > high").fetchone()[0]
            print("AUDIT candles:", n, "first:", first, "last:", last)
            print("AUDIT windows:", w, "reported rows:", total, "duplicates:", duplicates, "invalid OHLC:", invalid)
            if duplicates or invalid or n != total:
                raise RuntimeError("archive audit failed")
        finally:
            con.close()
        return
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
    con.execute("PRAGMA busy_timeout=5000")
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
            if requests:
                time.sleep(args.delay_seconds)
            values = fetch(key, cursor, stop, retries=args.retries)
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
                for row in rows:
                    existing = con.execute("SELECT open,high,low,close FROM candles WHERE minute_utc=?", (row[0],)).fetchone()
                    if existing is not None and any(abs(x-y)>0.000001 for x,y in zip(existing,row[1:])):
                        raise RuntimeError("conflicting candle in existing archive at " + row[0])
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
