"""V9.5 SELL research challenger: offline, non-deployed, no broker connections.

Compares historical candle-window SELL opportunities and a predefined
support-location veto. Reports chronological holdout separately. This is
exploratory research, NOT an executable V9.4 strategy or a performance claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = (8, 10, 12, 15, 20)


def analyze(windows: pd.DataFrame, candles: pd.DataFrame) -> dict:
    required = {"model_time", "window", "decision", "outcome", "independent_entry"}
    if not required.issubset(windows):
        raise ValueError("Missing window comparison fields")
    if not {"model_time", "distance_to_support_atr"}.issubset(candles):
        raise ValueError("Missing support-distance evidence")
    w = windows.copy()
    c = candles[["model_time", "distance_to_support_atr"]].copy()
    for frame in (w, c):
        frame["model_time"] = pd.to_datetime(frame["model_time"], utc=True)
    c = c.drop_duplicates("model_time")
    w["window"] = pd.to_numeric(w["window"], errors="coerce")
    w["outcome_r"] = pd.to_numeric(w.get("outcome_r"), errors="coerce")
    w["independent_entry"] = w["independent_entry"].astype(str).str.lower().eq("true")
    c["distance_to_support_atr"] = pd.to_numeric(c["distance_to_support_atr"], errors="coerce")
    merged = w.merge(c, on="model_time", how="left", validate="many_to_one")
    results = {}
    for window in WINDOWS:
        subset = merged[(merged.window == window) & (merged.decision == "SELL") & merged.independent_entry].sort_values("model_time")
        # Never treat unresolved outcomes as losses or wins.
        resolved = subset[subset.outcome.isin(["WIN", "LOSS"]) & subset.outcome_r.notna()].copy()
        if resolved.empty:
            results[str(window)] = {"status": "INSUFFICIENT_RESOLVED_TRADES", "candidates": int(len(subset))}
            continue
        split = max(1, int(len(resolved) * 0.7))
        periods = {"development": resolved.iloc[:split], "holdout": resolved.iloc[split:]}
        details = {}
        for name, frame in periods.items():
            if frame.empty:
                details[name] = {"status": "INSUFFICIENT_DATA"}
                continue
            # Fixed, transparent research rule; not fitted to holdout outcomes.
            near_support = frame.distance_to_support_atr.notna() & (frame.distance_to_support_atr >= 0) & (frame.distance_to_support_atr < 1.0)
            eligible = frame[~near_support]
            details[name] = {
                "baseline_n": int(len(frame)),
                "baseline_wins": int((frame.outcome == "WIN").sum()),
                "baseline_mean_r": round(float(frame.outcome_r.mean()), 4),
                "support_rejected_n": int(near_support.sum()),
                "support_rejected_wins": int((frame.loc[near_support, "outcome"] == "WIN").sum()),
                "support_rejected_losses": int((frame.loc[near_support, "outcome"] == "LOSS").sum()),
                "candidate_n": int(len(eligible)),
                "candidate_wins": int((eligible.outcome == "WIN").sum()),
                "candidate_mean_r": round(float(eligible.outcome_r.mean()), 4) if len(eligible) else None,
                "missing_support_distance": int(frame.distance_to_support_atr.isna().sum()),
            }
        results[str(window)] = {"status": "EXPLORATORY", "periods": details}
    return {
        "description": "Fixed near-support veto (<1 ATR), exploratory candle-window dataset, independent entries only.",
        "limitations": [
            "This candle-window sample is not identical to 62 live-watcher paper SELL signals.",
            "Chronological 70/30 split does not purge overlapping forward-outcome windows.",
            "Support distance may be derived from a different research feed; timestamp equality is not proof of quote parity.",
            "No original adaptive ATR multipliers, spread/slippage modeling, or true execution confirmation.",
            "Do not promote this filter to production without stronger validation.",
        ],
        "windows": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {
        (ROOT / "candle_window_comparison_v94.csv").resolve(),
        (ROOT / "candle_dynamics_m15_v94.csv").resolve(),
    }:
        parser.error("Cannot overwrite input")
    result = analyze(
        pd.read_csv(ROOT / "candle_window_comparison_v94.csv"),
        pd.read_csv(ROOT / "candle_dynamics_m15_v94.csv"),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for k, v in result["windows"].items():
        print("WINDOW", k, json.dumps(v))


if __name__ == "__main__":
    main()
