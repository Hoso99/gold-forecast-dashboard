# V9.4 48-M15 Support/Resistance + Location Research

Research only. **Do not replace the live V9.4 entry watcher or candle-power engine.**

This module adds causal (no-look-ahead) market-location features using the prior
48 completed M15 candles:

- nearest resistance and support
- distance to each level in ATR units
- near-resistance / near-support flags
- resistance-rejection flag
- support-break flag
- room below price before support
- SELL-location score/class
- component ablation
- room-below-support threshold search

## Purpose

The persistence research showed that simply making candle filters stricter
removes many signals without creating a clearly stronger out-of-sample edge.
This test asks a different question: **does WHERE a bearish candidate occurs
improve its subsequent 15/30/60/120-minute direction?**

## Integration with candle_dynamics_v94.py

Preferred usage inside the historical research script:

```python
from sr_location_research_v94 import add_sr_location_features, summarize_sr_location

research_df = add_sr_location_features(research_df, lookback=48)
summarize_sr_location(research_df, bearish_col="bearish_candidate")
```

Use the actual dataframe variable and bearish-candidate column names already
present in your current `candle_dynamics_v94.py`.

The live model remains unchanged until this historical research is validated.
