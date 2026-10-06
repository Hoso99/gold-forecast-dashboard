# V9.4 H4 Context Research

Research only; live V9.4 unchanged.

- Reconstructs H4 from M15.
- Requires all 16 M15 candles in each H4 candle.
- Uses only H4 candles whose end time is <= the M15 signal time.
- Includes a no-lookahead assertion.
- Uses the existing chronological 70/30 split and 8-M15 purge.
- Reports BEARISH / NEUTRAL / BULLISH H4 context at 15m, 30m, 60m and 120m.

Outputs:
- candle_dynamics_h4_context_summary_v94.csv
- candle_dynamics_h4_context_detail_v94.csv
