"""V9.5 research-only audit of committed M1 OHLC data.

No trading, alerts, broker calls, or changes to V9.4. Reports integrity
and coverage; does NOT validate provider timestamp semantics or profitability.
Run: python research/audits/v95_m1_data_audit.py
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "v94_forward_m1.csv"


def audit(path: Path = DATA) -> dict:
    timestamps = []
    invalid = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"datetime", "open", "high", "low", "close"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing required OHLC columns")
        for row_number, row in enumerate(reader, 2):
            try:
                ts = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    raise ValueError("Naive timestamp")
                ts = ts.astimezone(timezone.utc)
                o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
                import math
                if not all(math.isfinite(x) and x > 0 for x in (o, h, l, c)):
                    raise ValueError("Nonfinite or nonpositive OHLC")
                if h < max(o, c, l) or l > min(o, c, h):
                    raise ValueError("OHLC inconsistent")
                timestamps.append(ts)
            except (ValueError, TypeError, KeyError) as exc:
                invalid.append({"line": row_number, "reason": str(exc)})
    unique = sorted(set(timestamps))
    duplicates = len(timestamps) - len(unique)
    missing = []
    if unique:
        observed = set(unique)
        cursor = unique[0]
        while cursor <= unique[-1]:
            if cursor not in observed:
                missing.append(cursor)
            cursor += timedelta(minutes=1)
    # Count complete aligned blocks only; incomplete blocks are not usable
    # for causal M5/M15 confirmation.
    counts = {}
    for minutes in (5, 15):
        groups = Counter(ts.replace(minute=(ts.minute // minutes) * minutes, second=0, microsecond=0)
                         for ts in unique)
        counts[f"m{minutes}"] = {
            "complete_blocks": sum(n == minutes for n in groups.values()),
            "incomplete_blocks": sum(n != minutes for n in groups.values()),
        }
    return {
        "status": "DATA_QUALITY_ONLY_NOT_TRADING_VALIDATION",
        "source": str(path),
        "rows": len(timestamps) + len(invalid),
        "valid_rows": len(timestamps),
        "invalid_rows": invalid[:20],
        "duplicate_timestamps": duplicates,
        "first_utc": unique[0].isoformat() if unique else None,
        "last_utc": unique[-1].isoformat() if unique else None,
        "missing_minutes_within_observed_range": len(missing),
        "first_missing_utc": [t.isoformat() for t in missing[:10]],
        "aligned_bars": counts,
        "timestamp_semantics": "UNVERIFIED_OPEN_STAMP_ASSUMPTION",
        "limits": [
            "Gaps can include expected market closures; not all are feed failures",
            "No provider timestamp confirmation",
            "No historical bid/ask, spreads, slippage, or broker fills",
            "No V9.5 SELL entry or dynamic EXIT profitability inference",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
