# V9.5 time-integrity review — 2026-10-11

## Evidence
- Corrected research CI run [38144010294](https://github.com/Hoso99/gold-forecast-dashboard/actions/runs/38144010294) succeeded; existing 19 reliability tests passed.
- Source audit located `research_h4_context` and `research_h1_context` in `candle_dynamics_v94.py`, rather than separate H1/H4 Python files.
- H4 aggregation uses `resample("4h", label="left", closed="left")`, requires 16 M15 observations, and sets `h4_end = h4_start + 4h`. H1 similarly requires 4 M15 observations and sets `h1_end = h1_start + 1h`.
- Both functions join via `merge_asof(..., left_on="signal_time", right_on="h4_end"/"h1_end", direction="backward")` and assert that joined higher-timeframe end is not later than signal time.
- `candle_dynamics_v94.py` contains forward outcome columns and `false_sell_60m`. These must remain labels only, never predictors.

## Unresolved before claiming lookahead safety
1. Establish whether the M15 source `model_time` represents **candle open** or **candle close**. If it is candle-open time, the current H1/H4 end-time join can expose the last M15 candle at the boundary before that candle has completed.
2. Confirm complete bars are contiguous and unique: a count of 4 or 16 alone does not prove timestamps are unique or all intervals present.
3. Run adversarial timestamp tests at H1/H4 boundaries, gaps, duplicate timestamps, and the most recent incomplete candle.
4. Confirm the SELL power, H4 context, and structural location values in the historical CSV were all computed from the same point-in-time snapshot.
5. Evaluate independent, purged, chronological trade-level outcomes with costs, SL and TP before considering promotion.

## Decision
**Research-only; NOT approved for live deployment.** A successful source-inventory job is not proof of time integrity. Keep live V9.4 unchanged.
