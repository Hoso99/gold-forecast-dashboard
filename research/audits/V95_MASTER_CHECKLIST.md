# V9.5 SELL-only development checklist

Status definitions: RESEARCH = exploratory code or analysis exists, NOT validated for live use; PENDING = no verified complete V9.5 implementation; BASELINE = V9.4 requirement to preserve. Checkboxes are not implementation attestations.

## Signal direction, entry and context
- [ ] BASELINE: SELL-only mode; do not introduce BUY execution or alerts.
- [ ] RESEARCH: compare 8/10/12/15/20 M15 candle windows against V9.4 ten-candle baseline, logging both SELL and WAIT.
- [ ] RESEARCH: 10-candle SELL power, buying/selling pressure and acceleration; distinguish Biquote pressure from computed candle power.
- [ ] PENDING: four low-correlation signal modules with independently documented consensus.
- [ ] RESEARCH: H1/H4 completed-candle trend alignment, S/R and pivots, location filter, break/rejection, bearish structure.
- [ ] PENDING: institutional/liquidity and volume proxies; identify unavailable L2/COMEX data honestly.
- [ ] PENDING: EMA/RSI/momentum/Elliott research without future leakage.
- [ ] PENDING: M5 early SELL confirmation, reversal warning, false-SELL avoidance, and missed-move detection.
- [ ] PENDING: establish M1/M5/M15 timestamp meaning, continuity, data-source parity, and bar availability before M5 backtest.

## Risk, exit and execution
- [ ] BASELINE: mandatory M15 swing-high plus adaptive ATR SL; minimum 2R TP; never widen stops.
- [ ] BASELINE: 2% planned risk, daily realized-loss lock, no martingale/grid/averaging down.
- [ ] PENDING: adapt SL/TP to Biquote volatility and event buildup; maintain structural feasibility.
- [ ] PENDING: test partial profit, break-even, M5 early exits and trailing alternatives against fixed 2R.
- [ ] PENDING: cost/spread/slippage, bid/ask, stop/target same-bar ambiguity, stale prices, quote consistency.
- [ ] PENDING: distinguish quote-triggered entry alert, hypothetical signal, and broker-confirmed execution.

## Data, operations and safety
- [ ] BASELINE: public/nonbroker data, Biquote events and SELL pressure, high-impact macro including oil inventories, Cyprus/UTC conversions.
- [ ] RESEARCH: closed-market handling, duplicate alerts, threshold checks, evidence journals.
- [ ] PENDING: SELL-only Telegram entry/SL/TP/2R alerts, confirmed/blocked reasons, M5 warnings, schedule and delivery checks.
- [ ] PENDING: Streamlit/dashboard vs watcher signal parity and quote parity; GitHub Actions timing limitations.
- [ ] PENDING: no future data in predictors, independent chronological purged holdout, trade-level SL/TP with costs, drawdown and risk-adjusted comparison, sensitivity and robustness.
- [ ] PENDING: retain V9.4 live unchanged until V9.5 review, explicit approval, controlled deployment and rollback plan.

## Research findings (not deployment approval)
- Initial near-support veto worsened 10-candle holdout mean from -0.25R (20 resolved) to about -0.3684R (19 resolved); DO NOT DEPLOY.
- Context directional accuracy alone did not prove improved trading performance.
- V9.4 historical journal: 62 hypothetical SELL alerts (13 WIN, 40 LOSS, 9 OPEN), not broker executions; missing original ATR multiple in all 62.
- Existing `full_history_m15_m5.py` contains exploratory M1-derived M5/M15 confirmation; it is NOT a validated V9.5 entry/exit system. Audit timestamp assumptions, data gaps and outcomes before reusing.
- Research CI passing does not establish lookahead safety or profitability.

## Immediate sequence
1. Audit M1-derived M5/M15 candle alignment, completed-bar availability and missing/duplicate intervals.
2. Run a causal, cost-aware M5 confirmation challenger against unchanged M15 baseline on purged chronological holdout.
3. Test structural entry/SL/TP/exit variants with clear UNKNOWN cases when historical inputs are absent.
4. Verify V9.5 alerts and deployment separately, only after user approval.

**Scope: research branch only. Never merge, deploy or modify live V9.4 without explicit user approval.**

## Progress update — 2026-10-11
- [x] RESEARCH ONLY: M1-derived M5/M15 completeness audit executed in CI; 12 M1 gaps, 12 incomplete M5, 11 incomplete M15. Timestamp semantics still unverified.
- [x] RESEARCH ONLY: M15 vs mandatory M5 confirmation compared on chronological holdout (421 M15 vs 274 confirmed); M5 worsened 60-minute down-rate (48.46% to 46.72%) and improved 120-minute down-rate (45.61% to 47.08%). Not validated for trading.
- [x] RESEARCH CODE ADDED, NOT EXECUTED: delayed M5 reversal-warning study at research/audits/v95_m5_reversal_warning_study.py.
- [ ] Run and inspect reversal-warning study; workflow registration attempt was blocked, so do not mark it tested.
- [ ] Verify M1 timestamp semantics with source/provider and audit alignment before interpreting M5 warning as causal.
- [ ] Build cost-aware trade-level SL/TP, conservative same-bar resolution, and independent holdout before live promotion.
- [ ] Complete remaining signal, risk, Telegram and deployment checklist items above; do not deploy without explicit approval.
