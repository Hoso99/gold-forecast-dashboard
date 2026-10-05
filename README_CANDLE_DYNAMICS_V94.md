# V9.4 Candle Dynamics Research — Three-Filter Component Test

Research-only update. Live V9.4 is unchanged.

This version keeps the existing out-of-sample validation and adds a fixed ablation comparison of the three previously tested filters:
- directional efficiency >= 0.10
- reversal count <= 4
- SEG2 and SEG3 bearish persistence

It compares BASE, each filter alone, each pair, and ALL_3 on the same discovery/validation split. No new thresholds are optimized on the validation sample.

New output: `candle_dynamics_three_filter_components_v94.csv`.
