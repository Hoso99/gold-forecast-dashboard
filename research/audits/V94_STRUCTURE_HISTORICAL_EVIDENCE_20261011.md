# V9.4 Structural Gate — Historical Evidence Audit (2026-10-11)

**Scope:** research branch only; no production change or order execution.

## Source snapshots
- `trade_journal_v94.json`: 62 SELL hypothetical signals; 13 WIN, 40 LOSS, 9 OPEN. These are candle-derived paper outcomes, **not executed brokerage trades**.
- `evidence_journal_v94.json`: 206 model evaluations, including 24 SELL decisions and 182 WAIT decisions.
- All 24 SELL evaluations have a matching `model_time` and SELL side in the trade journal.

## Can we determine how many losing SELLs the corrected ACTIVE gate would block?
**No, not from these journals alone.** All 24 matched SELL evaluation records lack the exact `structure_atr_plan.status` and its `tp1` / `tp1_rr` at decision time. Their recorded 2R arithmetic TP is not equivalent to an independently validated M15 structural TP1. The S/R location features are evidence-only and cannot substitute for the missing structural plan.

Do **not** label any past LOSS as prevented or any past WIN as sacrificed without reconstructing the historical completed-M15 candle windows, contemporaneous entry quote, and the same structure/ATR plan inputs.

## Reproducible next step
1. Obtain timestamp-aligned historical completed M15 OHLC candles spanning each signal's required lookback, and preserve the source/time zone.
2. Rebuild the original decision-time plan with `structure_atr_plan("SELL", gold, atr_multiple=adaptive_atr_multiple, min_tp1_rr=2.0, swing_lookback=48, cost_bps=10, entry_price=original_entry)`.
3. Preserve the historical ATR multiple from the original signal where available; flag cases without sufficient inputs as **UNKNOWN**, not blocked.
4. Compare plan status, `tp1_rr`, and observed journal status for each record. Report counts of blocked WIN, blocked LOSS, blocked OPEN, and UNKNOWN separately.
5. Account for lookahead, intrabar SL/TP ambiguity, and hypothetical execution costs before any performance claim.

## Verified regression checks
GitHub Actions run 38140182144 passed 17 offline checks on the research branch. They do not constitute a historical market replay or prove future profitability.

**Production V9.4, SELL-only behavior, SL/TP, risk settings, Telegram, and scheduled workflows remain unchanged.**
