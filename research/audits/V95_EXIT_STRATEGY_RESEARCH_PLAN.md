# V9.5 SELL-only exit strategy research protocol

Status: HYPOTHESES ONLY. Not validated, no production changes, no Telegram changes.

## Why
Prior 120-minute structural + 1.5 ATR stop, fixed 2R target, illustrative 0.30 point cost:
holdout M15 421 signals, 26 STOP, 4 TARGET, 391 TIMEOUT, mean -0.0666R;
M15+M5 274 signals, 15 STOP, 0 TARGET, 259 TIMEOUT, mean -0.0558R.
The overwhelming timeout rate makes a 120m/2R combination worth challenging; it does NOT prove stops are too wide.

## Primary challenger: structure/ATR initial SL + partial + short Chandelier
- SELL only. Mandatory initial protective SL above invalidation swing high, plus ATR-based buffer.
- Never move the stop up (away from price) after entry.
- Candidate partial profit at +1R (50% position); remainder trailing SELL Chandelier stop: min(previous_stop, lowest_low_since_entry + k * completed_M5_ATR14). k=2, 2.5, 3 as research grid, not production defaults.
- Activate trailing after partial only; all decisions use completed bars and next-bar execution, never intrabar lookahead.
- Compare a no-partial Chandelier variant and a fixed-target variant.

## Controlled challenger matrix
A: unchanged research baseline (10 M15 swing high + 1.5 ATR14, 2R TP, 120m expiry).
B: identical initial SL, TP at 1R, 1.5R, 2R; expiry 120/240/360m.
C: identical initial SL, 50% at +1R, remainder at +2R; expiry 120/240/360m.
D: identical initial SL, 50% at +1R, remainder M5 Chandelier trailing k=2/2.5/3; expiry 120/240/360m.
E: identical initial SL, full position M5 Chandelier after +1R; expiry 120/240/360m.
F: ATR-only initial SL at 1.5/2 ATR above entry, ONLY if above structure invalidation; otherwise skip, not silently widen or tighten structure stop.
For every candidate, initial SL is mandatory, no averaging down, planned account risk <=2%, daily loss lock preserved.

## Validation and implementation gates
1. Verify M1 timestamp meaning and M5/M15 completed-bar availability with original data provider before trusting results.
2. Entry next available quote/bar after signal; no same-bar future information.
3. M1 path for fill ordering; STOP first if SL and TP both touch same bar; gap-through stop priced adversely, not at perfect stop.
4. Spread/slippage sensitivity (including high-volatility cases), no invented live bid/ask.
5. One position at a time and overlapping-signal deduplication; portfolio equity, maximum drawdown, worst trade, time in market.
6. Chronological purged development/holdout; predeclare parameter grid, rank on development only; untouched holdout, sensitivity and confidence intervals.
7. Compare mean/median net R, profit factor, win rate, stop/target/timeout frequency, adverse/favorable excursions, duration, max drawdown, downside tail and number of trades.
8. Separately analyze Biquote normal/building/high event states only where timestamped historical data exist; otherwise mark unavailable.
9. Never promote to V9.5 alerts or live without explicit approval and rollback.

Research sources:
- https://www.tradingview.com/support/solutions/43000773013-chandelier-exit/
- https://onlinelibrary.wiley.com/doi/full/10.1111/irfi.12328
- https://link.springer.com/article/10.1186/s40854-025-00866-w
