"""V9.5 research-only historical SELL context audit.

Compare precomputed candidate flags on the same historical research rows.
Forward returns are outcomes ONLY, never predictors. No live integration.
"""
from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[2]
df = pd.read_csv(root / "candle_dynamics_production_parity_detail_v94.csv")
df["model_time"] = pd.to_datetime(df["model_time"], utc=True)
df = df.sort_values("model_time")
print("ROWS", len(df), "START", df.model_time.min(), "END", df.model_time.max())
flags = ("prod_sell_confirmed", "h4_bearish", "sr_good_sell", "prod_plus_context2")
for flag in flags:
    print("FLAG", flag, "values", df[flag].value_counts(dropna=False).to_dict())
for horizon in ("forward_30m", "forward_60m"):
    print("HORIZON", horizon)
    outcomes = pd.to_numeric(df[horizon], errors="coerce")
    # Directional price movement, NOT simulated SL/TP or realized trade R.
    for flag in flags:
        mask = df[flag].astype(str).str.lower().eq("true") & outcomes.notna()
        n = int(mask.sum())
        print(flag, "n", n, "down_fraction", round(float((outcomes[mask] < 0).mean()), 4) if n else None,
              "mean_price_change", round(float(outcomes[mask].mean()), 4) if n else None)
print("WARNING: these are descriptive in-sample associations, not validated causal or live trading performance.")
print("WARNING: confirm H4 candle completion and candidate feature timestamps before using these flags.")
