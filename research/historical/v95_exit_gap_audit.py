"""Read-only audit of unmatched V9.5 research exit outcomes.

Usage:
  python3 research/historical/v95_exit_gap_audit.py \
    --report v95-adaptive-exit-challenger.json \
    --output v95-exit-gap-audit.json

Does not alter candles, live monitors, trades, or existing reports.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOT = Path("/home/ubuntu/v95-historical-research")
NAMES = [
    "twelve_xauusd_m1.sqlite3",
    "twelve_xauusd_m1_2021_2022.sqlite3",
    "twelve_xauusd_m1_2022_2023.sqlite3",
    "twelve_xauusd_m1_2023_2024.sqlite3",
    "twelve_xauusd_m1_2024_2025.sqlite3",
    "twelve_xauusd_m1_2025_2026.sqlite3",
    "twelve_xauusd_m1_2026_partial.sqlite3",
]
ONE = dt.timedelta(minutes=1)
MAX_HOLD = dt.timedelta(minutes=240)

def parse(stamp):
    t = dt.datetime.fromisoformat(stamp)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)

def candles(start, end):
    found = {}
    for name in NAMES:
        path = ROOT / name
        if not path.is_file():
            raise FileNotFoundError(path)
        uri = "file:" + quote(str(path), safe="/") + "?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            for stamp, o, h, l, c in db.execute(
                "SELECT minute_utc,open,high,low,close FROM candles "
                "WHERE minute_utc>=? AND minute_utc<=? ORDER BY minute_utc",
                (start.date().isoformat(), (end.date()+ONE).isoformat())
            ):
                t = parse(stamp)
                if start <= t <= end:
                    values = (o, h, l, c)
                    if t in found and found[t] != values:
                        raise ValueError("Conflicting overlapping historical bars at " + t.isoformat())
                    found[t] = values
    return sorted(found)

def inspect(row):
    entry = parse(row["entry_utc"])
    end = entry + MAX_HOLD
    times = candles(entry, end)
    after = [t for t in times if t > entry]
    gaps = []
    previous = entry
    for t in after:
        if t - previous != ONE:
            gaps.append({
                "last_observed_utc": previous.isoformat(),
                "next_observed_utc": t.isoformat(),
                "missing_minutes": int((t-previous)/ONE)-1,
            })
        previous = t
    expected = int(MAX_HOLD/ONE)
    return {
        "entry_utc": row["entry_utc"], "year": row["year"],
        "original_outcome": row["original_outcome"],
        "strict_outcome": row["strict_outcome"],
        "adaptive_outcome": row["adaptive_outcome"],
        "original_net_r": row.get("original_net_r"),
        "strict_net_r": row.get("strict_net_r"),
        "adaptive_net_r": row.get("adaptive_net_r"),
        "first_after_entry_utc": after[0].isoformat() if after else None,
        "last_available_utc": after[-1].isoformat() if after else None,
        "observed_minutes_after_entry": len(after),
        "expected_minutes_after_entry": expected,
        "reaches_240m": end in times,
        "first_gap": gaps[0] if gaps else None,
        "gap_count": len(gaps),
        "gaps": gaps[:8],
        "interpretation": (
            "Historical M1 gap detected: do not impute exit or R"
            if gaps else
            "No interior M1 gap; examine timeout, exit logic and dataset end"
        ),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=Path("v95-adaptive-exit-challenger.json"))
    parser.add_argument("--output", type=Path, default=Path("v95-exit-gap-audit.json"))
    args = parser.parse_args()
    if args.report.resolve() == args.output.resolve():
        parser.error("Input report and output must differ")
    report = json.loads(args.report.read_text())
    rows = report["pairs"]
    selected = [
        row for row in rows
        if any(row.get(arm+"_net_r") is None for arm in ("original", "strict", "adaptive"))
    ]
    audited = [inspect(row) for row in selected]
    result = {
        "research_only": True,
        "source_report": str(args.report),
        "total_pairs": len(rows),
        "unresolved_union": len(selected),
        "gap_detected": sum(x["gap_count"] > 0 for x in audited),
        "no_gap_detected": sum(x["gap_count"] == 0 for x in audited),
        "cases": audited,
        "caveat": "Diagnostic only; no hypothetical fills, no inferred net R, no live model changes.",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("EXIT_GAP_AUDIT", json.dumps({k:v for k,v in result.items() if k!="cases"}))
    for case in audited:
        print("CASE", case["entry_utc"], "original="+case["original_outcome"],
              "strict="+case["strict_outcome"], "adaptive="+case["adaptive_outcome"],
              "gap="+str(case["first_gap"]), "reaches_240m="+str(case["reaches_240m"]))
    print("RESEARCH_ONLY_GAP_AUDIT_COMPLETE")

if __name__ == "__main__":
    main()
