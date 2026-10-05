# V9.4 Candle Dynamics Research

Research-only package; it does not modify the live V9.4 model.

It implements the 13 requested areas: intracandle M1 path, movement size, directional efficiency, 1-5/6-10/11-15 timing, UTC/Cyprus time-of-day, acceleration/reversals, high/low sequencing, previous-M15 breakout continuation/rejection, prior-48-M15 support/resistance location, 15/30/60/120/240m follow-through, false SELL cases, volatility regimes, and SELL-perspective MAE/MFE.

## Resolution limits
M1 data reconstructs minute-to-minute behavior, not tick order inside a minute. If the M15 high and low occur in the same M1 bar, sequencing is marked ambiguous. Historical event regime is `UNKNOWN` because the current Biquote upcoming-events endpoint cannot truthfully reconstruct past events.

## Historical depth
Default is 15,000 M1 candles. This is NOT the same span as 15,000 M15 candles. Reconstructing 15,000 M15 candles requires roughly 225,000 M1 bars before closures; provider/API availability may limit this. Increase `DYNAMICS_M1_BARS` later if the plan permits.

## Install
Copy `candle_dynamics_v94.py` and `.github/workflows/candle-dynamics-v94.yml` into the repository, preserving paths. The existing `TWELVE_DATA_API_KEY` GitHub secret is used. Then manually run **V9.4 Candle Dynamics Research** in Actions.

## Multi-factor SELL search
The research script now compares combinations of directional efficiency, reversal limits, late SELL acceleration, persistence, HIGH_FIRST sequence, and volatility regime. It reports 15/30/60/120-minute SELL continuation rates, average forward movement, MFE/MAE, retained sample size, and a continuation ranking score. This is research-only and does not modify the live V9.4 entry watcher.

## Out-of-sample validation
The research now performs a chronological 70/30 discovery/validation split. The final 30% is not used to select the rules. Eight M15 candles are purged before the split to prevent the 120-minute forward outcome from leaking into validation. The top 20 discovery rules are then applied unchanged to the validation period. Outputs: `candle_dynamics_oos_metadata_v94.csv` and `candle_dynamics_oos_validation_v94.csv`.
