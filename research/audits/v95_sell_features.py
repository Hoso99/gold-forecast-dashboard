"""Research-only V9.5 SELL continuation/rejection feature comparison.

Predefined diagnostic features are compared independently on chronological
holdout samples; not an executable strategy or a production recommendation.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
w = pd.read_csv(ROOT / "candle_window_comparison_v94.csv")
c = pd.read_csv(ROOT / "candle_dynamics_m15_v94.csv")
w["model_time"] = pd.to_datetime(w["model_time"], utc=True)
c["model_time"] = pd.to_datetime(c["model_time"], utc=True)
c = c.drop_duplicates("model_time")
features = ["low_break_continuation", "high_break_rejection", "bearish_candidate", "false_sell_60m"]
merged = w.merge(c[["model_time"] + features], on="model_time", how="left", validate="many_to_one")
merged["window"] = pd.to_numeric(merged["window"], errors="coerce")
merged["outcome_r"] = pd.to_numeric(merged["outcome_r"], errors="coerce")
merged["independent_entry"] = merged["independent_entry"].astype(str).str.lower().eq("true")
results = {}
for window in (8, 10, 12, 15, 20):
    rows = merged[(merged.window == window) & (merged.decision == "SELL") &
                  merged.independent_entry & merged.outcome.isin(["WIN", "LOSS"]) &
                  merged.outcome_r.notna()].sort_values("model_time")
    cutoff = max(1, int(len(rows) * 0.7))
    holdout = rows.iloc[cutoff:]
    summary = {"resolved_n": int(len(rows)), "holdout_n": int(len(holdout)), "features": {}}
    for feature in features:
        # false_sell_60m uses future data and is DIAGNOSTIC ONLY, never a tradable filter.
        for subset_name, subset in (("development", rows.iloc[:cutoff]), ("holdout", holdout)):
            flags = subset[feature].astype(str).str.lower().eq("true")
            flagged = subset[flags]
            summary["features"].setdefault(feature, {})[subset_name] = {
                "flagged_n": int(len(flagged)),
                "flagged_wins": int((flagged.outcome == "WIN").sum()),
                "flagged_losses": int((flagged.outcome == "LOSS").sum()),
                "flagged_mean_r": round(float(flagged.outcome_r.mean()), 4) if len(flagged) else None,
            }
    results[str(window)] = summary
print("V9.5 independent historical feature audit (not live trade signals)")
print(json.dumps(results, indent=2))
print("WARNING: false_sell_60m is forward-looking and cannot be used as an entry filter.")
