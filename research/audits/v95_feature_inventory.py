"""V9.5 research: audit available pre-entry SELL pressure and H1/H4 fields.

No feature is promoted to production. Inspect data coverage and holdout
association, without using any forward-looking columns as predictors.
"""
from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parents[2]
names = (
    "candle_dynamics_full_chain_detail_v94.csv",
    "candle_dynamics_h1_context_detail_v94.csv",
    "candle_dynamics_h4_context_detail_v94.csv",
    "candle_dynamics_production_parity_detail_v94.csv",
)
for name in names:
    path = root / name
    frame = pd.read_csv(path, nrows=3)
    print("DATASET", name)
    print("COLUMNS", list(frame.columns))
    print("ROWS_SAMPLED", len(frame))
    print("TIMESTAMP_EXAMPLE", frame["model_time"].iloc[0] if "model_time" in frame and len(frame) else "unknown")
    print("CAUTION: column availability is not proof of point-in-time validity")
