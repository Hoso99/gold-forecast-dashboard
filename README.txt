V9.4 SELL CONTINUATION TIME-STABILITY RESEARCH

Research only. Live V9.4 is unchanged.

New outputs:
- candle_dynamics_continuation_stability_blocks_v94.csv
- candle_dynamics_continuation_stability_summary_v94.csv

The test evaluates fixed Continuation Score thresholds 60/65/70/75 across six chronological blocks. It purges the final 8 M15 candles between blocks to prevent 120-minute forward outcomes from leaking across block boundaries. No threshold is re-fit on the blocks.
