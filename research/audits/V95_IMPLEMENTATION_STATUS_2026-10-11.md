# V9.5 checklist implementation tracker — isolated research branch

**Never modify V9.4.** This file records verified scope, not a claim of trading superiority.

| Requirement | Current status | Evidence / remaining work |
|---|---|---|
| SELL-only paper decisions | Implemented, research | v95_paper_monitor.py; no broker orders |
| Twelve Data M1, completed M5/M15/H1/H4 | Implemented, source semantics unverified | M1 open-stamp assumed; missing-bar and stale checks |
| 10-candle pressure | Implemented proxy only | Candle bodies, NOT Biquote/order-book pressure |
| EMA, RSI, pivots, momentum | Diagnostics implemented | v95_indicators.py; not promoted as trade gates |
| H1/H4 trend and M15 breakout/location | Exploratory gates | Unvalidated historical thresholds |
| 8/10/12/15/20 M15 windows | Research pending | Require fair baseline, causal replay and WAIT journal |
| Four research voting modules | Implemented as diagnostics, NOT independent | Trend, structure, momentum, candle-flow votes logged; low correlation/edge still unverified |
| Elliott Wave, volume/liquidity proxies | Pending | Must be causal and explicitly labeled proxy |
| Biquote event/quote context | Implemented as optional research journaling, live unverified | Public bid/ask and high-impact US calendar incl. oil; no Biquote sell-pressure API assumed; no trade gate |
| High-impact calendar incl. oil inventories, Cyprus/UTC | Implemented optional context, live unverified | Explicit exact-time events only; no news-based trading gate |
| Adaptive ATR for event volatility | Pending | Current monitor uses structural + fixed 1.5 ATR |
| Minimum 2R target | Implemented paper | Entry uses structural SL and 2R |
| 2% risk / 3% UTC day loss lock | Prototype, audit pending | Requires V95_PAPER_EQUITY; paper-only ledger lacks full fill/cost accounting |
| Partial exits, break-even, trailing, reversal exits | Prototype / comparison pending | 31-variant exit research exists, no validated winner |
| Spread, slippage, stop-first, adverse gaps | Partial | Stop-first/adverse gaps in paper monitor; no full bid/ask cost model |
| Duplicate/retry-safe Telegram | Pending | Research labels exist; durable retry and delivery acknowledgment missing |
| Same Telegram chat as V9.4 | User preference confirmed; not configured on Oracle | Secrets must be provisioned securely in V9.5-only env |
| Oracle persistent service | Service unit authored, not installed/verified | Separate v95-research-monitor.service; activation requires review |
| Independent V9.4 comparison | Pending | Never modify V9.4; use read-only historic journals and matching periods |
| No future leakage / purged holdout | Pending | Required before any claim of improved accuracy |

## Promotion rule
No change to live V9.4 and no claim that V9.5 is better until independent chronological holdout demonstrates improved **net R after costs** and acceptable drawdown, false-SELL and missed-SELL trade-offs. V9.5 is research-only, not an executable recommendation.
