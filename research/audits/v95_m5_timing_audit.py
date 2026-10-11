"""Research-only audit of M1-derived M5/M15 bar completeness and timing.

No live signals, Telegram, broker, or production writes.
Usage: python research/audits/v95_m5_timing_audit.py
"""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def audit(path: Path) -> dict:
    raw = pd.read_csv(path, usecols=["datetime", "open", "high", "low", "close"])
    raw["datetime"] = pd.to_datetime(raw["datetime"], utc=True, errors="coerce")
    bad_times = int(raw.datetime.isna().sum())
    duplicate_times = int(raw.datetime.duplicated().sum())
    x = raw.dropna(subset=["datetime"]).sort_values("datetime")
    x = x.drop_duplicates("datetime", keep="last").set_index("datetime")
    delta = x.index.to_series().diff().dropna()
    gaps = int((delta > pd.Timedelta(minutes=1)).sum())
    subminute = int((delta < pd.Timedelta(minutes=1)).sum())
    result = {"source": path.name, "rows": len(raw), "invalid_timestamps": bad_times,
              "duplicate_timestamps": duplicate_times, "m1_gaps": gaps,
              "subminute_intervals": subminute, "timestamp_semantics": "UNVERIFIED"}
    for mins in (5, 15):
        grp = x.groupby(x.index.floor(f"{mins}min"))
        count = grp.size()
        # Check actual constituent timestamps rather than count alone.
        expected = pd.Timedelta(minutes=1)
        def complete(g):
            return (len(g) == mins and
                    g.index[0] == g.index[0].floor(f"{mins}min") and
                    g.index[-1] == g.index[0] + pd.Timedelta(minutes=mins-1) and
                    bool((g.index.to_series().diff().dropna() == expected).all()))
        valid = grp.apply(complete)
        result[f"m{mins}"] = {"windows": int(len(valid)),
                             "complete": int(valid.sum()),
                             "incomplete": int((~valid).sum()),
                             "first_completed_end": str((valid[valid].index.min() + pd.Timedelta(minutes=mins))) if valid.any() else None,
                             "last_completed_end": str((valid[valid].index.max() + pd.Timedelta(minutes=mins))) if valid.any() else None}
    # Open- vs close-stamped M1 feed cannot be inferred safely from OHLC alone.
    result["decision"] = ("REVIEW_REQUIRED" if bad_times or duplicate_times or subminute or
                          result["m5"]["incomplete"] or result["m15"]["incomplete"] else
                          "COMPLETENESS_OK_TIMESTAMP_SEMANTICS_UNVERIFIED")
    return result


if __name__ == "__main__":
    result = audit(ROOT / "candle_dynamics_m1_v94.csv")
    print(json.dumps(result, indent=2))
