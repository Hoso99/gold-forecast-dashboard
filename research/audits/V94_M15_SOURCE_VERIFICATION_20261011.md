# V9.4 historical M15 source verification — 2026-10-11

Research-only verification; **no live changes**.

- Source: `candle_dynamics_m15_v94.csv` on the research branch.
- 14,991 rows with `model_time`, `open`, `high`, `low`, `close`, and `atr14` columns.
- UTC candle timestamp range: 2026-05-05 07:30 to 2026-10-08 13:15.
- `trade_journal_v94.json` contains 62 SELL signals.
- 56/62 SELL signal timestamps match the historical CSV exactly after ISO timestamp normalization.
- Six unmatched model times: 2026-10-08 15:00, 2026-10-09 09:00, 10:30, 11:00, 11:30, 14:30 (UTC).
- 0/62 journal signals record the original adaptive `atr_multiple`.

## Interpretation

The M15 CSV is a promising source for an **exploratory** structural sensitivity replay, but it does not establish exact decision-time provenance or the missing original Biquote/event-driven ATR setting. Do not treat reconstructed decisions as proof that the live filter would have prevented a historical loss.

A transparent sensitivity analysis may evaluate ATR multiples 1.50, 1.75, 2.00 and 2.25 separately, with independent counts of PASS, BLOCK, UNKNOWN by historical WIN/LOSS/OPEN. The six unmatched timestamps remain UNKNOWN. Exclude any lookahead-derived columns such as `forward_15m` from decision inputs. Require candle completeness and timing checks.

Do not modify or deploy the live V9.4 system.
