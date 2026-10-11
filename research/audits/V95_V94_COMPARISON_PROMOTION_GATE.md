# V9.4 vs V9.5 SELL research promotion gate

Purpose: reduce failed SELL signals **without** selecting a filter based only on the same data used to tune it.

## Frozen baselines and input parity
- V9.4 baseline must use the original historical V9.4 entry decisions, not a newly invented approximation. Keep V9.4 code and Telegram unchanged.
- V9.5 candidate: completed M5 bearish momentum + M15 structure + H1/H4 bearish trend + 10-M1 candle-body SELL proxy + older-support downside room. These are exploratory proxies, not Biquote pressure.
- Use identical instrument, data vendor, timestamp semantics, available information, execution delay, spread/slippage assumptions and periods. If parity cannot be established, report UNKNOWN rather than a numerical improvement.
- Record both SELL and WAIT decisions for 8/10/12/15/20 M15 windows. Evaluate missed favorable declines after WAIT as well as losing SELLs.

## Validation
1. Audit Twelve Data UTC M1 open/close timestamp semantics and no gaps/duplicates, and preserve a strict completed-bar cutoff for M5/M15/H1/H4.
2. Build a reproducible V9.4-vs-V9.5 journal with UTC decision time, input bars, proxy pressure, indicators, support/ATR, SELL/WAIT reason, hypothetical entry, SL/TP, M1 path, costs, exit time and net R.
3. Use chronological development and untouched purged holdout. Tune thresholds only on development. No same-bar fills at decision candle close; conservative stop-first when SL/TP collide and adverse gap fills.
4. Report SELL count, losing SELL count and rate, mean/median net R, profit factor, worst trade, max drawdown, 95% uncertainty, stop/target/timeout, missed SELL opportunities, sensitivity to spread/slippage and 8/10/12/15/20 windows.
5. Compare all candidate versions against V9.4 on the *same* holdout. A higher win rate with worse net R or worse drawdown is not sufficient.
6. Do not claim better accuracy or activate trading-decision alerts until independent holdout improves net R and downside risk, and all mandatory controls (2% risk, 3% loss lock, Biquote calendar/volatility, idempotent Telegram and state recovery) are verified.

## Known blockers as of 2026-10-11
- V9.5 paper monitor's support/pressure thresholds are not calibrated on holdout.
- Biquote event/volatility integration and cost model are absent.
- Partial-exit acknowledgment, daily loss accounting and position lifecycle need additional audit.
- The offline dynamic-exit holdout remained negative; no production promotion.
- Oracle service has not been deployed or verified.
