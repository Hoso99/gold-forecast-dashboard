"""Read-only Oracle V9.5 gap-aware feasibility probe; never runs evaluate()."""
import datetime as dt
import math
import sqlite3
from pathlib import Path

from v95_gap_aware_gate import check

UTC = dt.timezone.utc
DB = Path("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")


def load(db_path=DB, limit=2500):
    with sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True) as db:
        records = db.execute(
            "SELECT minute, open, high, low, close FROM candles ORDER BY minute DESC LIMIT ?",
            (limit,)
        ).fetchall()
    rows = []
    for minute, o, h, l, c in records:
        t = dt.datetime.fromisoformat(minute)
        vals = [float(x) for x in (o, h, l, c)]
        if (t.tzinfo is None or t.utcoffset() != dt.timedelta(0)
                or t.second or t.microsecond or
                not all(math.isfinite(v) and v > 0 for v in vals) or
                not vals[2] <= min(vals[0], vals[3]) <= max(vals[0], vals[3]) <= vals[1]):
            raise ValueError("Invalid original Biquote candle")
        rows.append(dict(zip(("t", "o", "h", "l", "c"), (t, *vals))))
    return sorted(rows, key=lambda x: x["t"])


def aggregate(rows, minutes):
    """Exact Oracle monitor aggregation behavior, without importing monitor side effects."""
    out = []
    groups = {}
    for x in rows:
        midnight = x["t"].replace(hour=0, minute=0, second=0, microsecond=0)
        minute_of_day = x["t"].hour * 60 + x["t"].minute
        start = midnight + dt.timedelta(minutes=(minute_of_day // minutes) * minutes)
        groups.setdefault(start, []).append(x)
    for start, chunk in sorted(groups.items()):
        expected = [start + dt.timedelta(minutes=i) for i in range(minutes)]
        if len(chunk) != minutes or [x["t"] for x in chunk] != expected:
            continue
        out.append({"t": start, "o": chunk[0]["o"],
                    "h": max(y["h"] for y in chunk),
                    "l": min(y["l"] for y in chunk),
                    "c": chunk[-1]["c"]})
    return out


def main():
    rows = load()
    now = dt.datetime.now(UTC)
    ok, reason, detail = check(rows, aggregate, now=now)
    print("MODE: READ_ONLY; NO STATE, DATABASE, JOURNAL OR TRADE WRITES")
    print("M1 ROWS:", len(rows))
    print("LATEST M1:", rows[-1]["t"].isoformat() if rows else "NONE")
    print("GATE:", "READY" if ok else "WAIT_DATA")
    print("REASON:", reason)
    for name, value in detail.items():
        print(name, value)
    print("NOTE: This is a feasibility probe, not a deployed integration or SELL signal.")


if __name__ == "__main__":
    main()
