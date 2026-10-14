"""Read-only V9.5 candidate recovery inspector. No candle DB writes or trading."""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
DB = Path.home() / "v95-detector-dev/research/feed_validation/biquote_m1.sqlite3"


def parse_utc(value):
    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0) or stamp.second or stamp.microsecond:
        raise ValueError("Expected UTC-aligned minute")
    return stamp.astimezone(UTC)


def market_minute(stamp):
    local = stamp.astimezone(NY)
    day, hour = local.weekday(), local.hour
    if day == 5 or (day == 4 and hour >= 17) or (day == 6 and hour < 17):
        return False
    return not (day < 4 and hour == 17)


def read_neighbors(path, stamp):
    before = (stamp - dt.timedelta(minutes=1)).isoformat()
    after = (stamp + dt.timedelta(minutes=1)).isoformat()
    with sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True) as db:
        rows = db.execute(
            "SELECT minute, open, high, low, close, ticks FROM candles WHERE minute IN (?,?,?)",
            (before, stamp.isoformat(), after)
        ).fetchall()
    candles = {row[0]: row for row in rows}
    if stamp.isoformat() in candles:
        raise ValueError("Target candle already exists")
    if before not in candles or after not in candles:
        raise ValueError("Adjacent Biquote candles unavailable")
    return candles[before], candles[after]


def candidate(payload, stamp):
    if not isinstance(payload, dict) or payload.get("status") == "error" or not isinstance(payload.get("values"), list):
        raise ValueError("Provider returned no candle values")
    matches = []
    for row in payload["values"]:
        try:
            t = dt.datetime.fromisoformat(row["datetime"])
            if t.tzinfo is None:
                t = t.replace(tzinfo=UTC)  # Request explicitly uses timezone=UTC.
            if parse_utc(t.isoformat()) != stamp:
                continue
            o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            if all(math.isfinite(v) and v > 0 for v in (o, h, l, c)) and l <= min(o, c) <= max(o, c) <= h:
                matches.append((o, h, l, c))
        except (ValueError, KeyError, TypeError):
            continue
    if len(matches) != 1:
        raise ValueError("Expected one valid matching UTC candle")
    return matches[0]


def inspect(path, stamp, payload=None):
    if not market_minute(stamp):
        raise ValueError("Minute is outside standard gold session")
    previous, following = read_neighbors(path, stamp)
    result = {"mode": "READ_ONLY", "minute_utc": stamp.isoformat(),
              "status": "AWAITING_PROVIDER_CANDIDATE"}
    if payload is not None:
        o, h, l, c = candidate(payload, stamp)
        result["status"] = "CANDIDATE_QUARANTINED"
        result["provider"] = "Twelve Data"
        result["ohlc"] = {"open": o, "high": h, "low": l, "close": c}
        result["previous_biquote_close_difference"] = round(abs(o - previous[4]), 6)
        result["next_biquote_open_difference"] = round(abs(c - following[1]), 6)
        result["decision"] = "REVIEW_REQUIRED_NO_AUTOMATIC_MERGE"
    return result


def fetch_once(key, stamp):
    query = urlencode({
        "symbol": "XAU/USD", "interval": "1min", "timezone": "UTC",
        "start_date": (stamp - dt.timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "end_date": (stamp + dt.timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "outputsize": 8, "apikey": key
    })
    try:
        with urlopen(Request("https://api.twelvedata.com/time_series?" + query), timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError("Provider HTTP status " + str(exc.code)) from None
    except URLError:
        raise RuntimeError("Provider connection failed") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB)
    parser.add_argument("--minute", required=True)
    parser.add_argument("--fetch-once", action="store_true",
                        help="Explicit opt-in for exactly one credit-consuming provider request")
    args = parser.parse_args()
    try:
        stamp = parse_utc(args.minute)
        report = inspect(args.db, stamp)
        if args.fetch_once:
            key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
            if not key:
                raise ValueError("TWELVE_DATA_API_KEY environment variable missing")
            report = inspect(args.db, stamp, fetch_once(key, stamp))
        print(json.dumps(report, indent=2))
    except (ValueError, RuntimeError, sqlite3.Error, OSError) as exc:
        print(json.dumps({"status": "WAIT_DATA", "error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
