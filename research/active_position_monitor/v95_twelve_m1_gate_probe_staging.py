"""Read-only V9.5 single-provider Twelve Data cache readiness probe.

Loads genuine cached M1 rows, then applies the existing V9.5 aggregate and
entry data gate without running the paper engine or touching state.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

from v95_paper_monitor import aggregate
from v95_gap_aware_gate import check

UTC = dt.timezone.utc


def probe(path, now=None):
    now = now or dt.datetime.now(UTC)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        records = db.execute(
            "SELECT minute_utc, open, high, low, close FROM twelve_m1 "
            "ORDER BY minute_utc DESC LIMIT 2500"
        ).fetchall()
    rows = []
    for stamp, o, h, l, c in reversed(records):
        t = dt.datetime.fromisoformat(stamp)
        if t.tzinfo is None or t.utcoffset() != dt.timedelta(0):
            raise ValueError("cache timestamps must be UTC")
        if t + dt.timedelta(minutes=1) > now - dt.timedelta(seconds=10):
            continue
        rows.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    eligible, reason, details = check(rows, aggregate, now=now)
    return {
        "source": "TWELVE_DATA_ONLY",
        "cached_completed_rows": len(rows),
        "latest_m1_utc": rows[-1]["t"].isoformat() if rows else None,
        "indicator_gate_eligible": eligible,
        "indicator_gate_reason": reason,
        "indicator_gate_details": details,
        "paper_engine_executed": False,
        "entry_authorized": False,
        "live_or_paper_state_modified": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path,
                   default=Path("/home/ubuntu/v95-recovery-staging/twelve_m1_cache.sqlite3"))
    args = p.parse_args()
    print(json.dumps(probe(args.cache), indent=2))


if __name__ == "__main__":
    main()
