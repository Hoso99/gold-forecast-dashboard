# Gold Version 9.3 — Calibrated Regime-Ensemble Challenger

Version 9.3 is separate from Version 8.2.5. It does not replace `app_v82.py` or `forecast_ledger_v825.sqlite` and contains no broker execution.

## Design

- Slow, release-timestamped macro variables classify the regime as BULLISH, BEARISH or NEUTRAL.
- Three diverse models form a calibrated next-hour ensemble. Their weights are
  learned only from each fold's held-out calibration segment; equal weights are
  retained whenever calibration weighting does not improve Brier score.
- Every fold has a purged fit window, a separate calibration window and an untouched test window.
- Causal regime, normalized cross-asset shock and market-session features time the candidate.
- A robust jump detector compares each completed candle with a shifted 96-bar baseline, audits cross-asset co-shocks, and blocks release for four candles after an abnormal move.
- A technical-rejection engine waits for the four-bar cooldown, tests whether price reversed through the shock midpoint, and remains weightless until 30 holdout cases pass accuracy, Wilson-bound and profit-factor gates.
- The official Investing.com calendar widget displays three-star importance, previous, forecast and actual values. The user-confirmed three-star USD event checkbox blocks release within the next hour; widget data is not scraped or stored.
- Official release times are converted from U.S. Eastern time and displayed in GMT. After every model run, an event notice reports lockout, elevated preparation risk, or no scheduled high-impact event and names the relevant releases.
- Expected movement must exceed twice the configured trading cost.
- Evaluation uses every second 15-minute observation so 30-minute outcomes do not overlap.
- Version 9.3 uses its own 30-minute walk-forward validation; Version 8.2.5 is not a comparable one-hour benchmark.
- A side-specific selective-prediction gate requires at least 30 comparable
  purged out-of-sample BUY or SELL signals and a 90% Wilson accuracy lower
  bound of at least 50%. Weak evidence remains NO EDGE.
- The three ensemble members must not disagree by more than 12 probability
  points for an actionable signal.
- Quantile forecasts are expanded with a fold-local split-conformal correction,
  and the median forecast receives a robust calibration-window bias correction.
- The Decision tab separates the slow macro background from a causal short-term
  technical trend built from one-hour momentum, two-hour momentum, 8/32 EMA
  alignment and recent candle persistence.
- An all-source directional score reports BUY LEAN or SELL LEAN using the
  calibrated statistical probability, short-term trend, expected move, slow
  macro background and confirmed cross-venue pressure. It is explanatory and
  cannot override failed validation, transaction-cost or event gates.
- A high-confidence four-venue pressure conflict or an opposing short-term technical trend
  blocks an otherwise actionable candidate.
- A separate five-minute XAU/USD exhaustion-and-break detector can issue an
  EARLY BUY WARNING or EARLY SELL WARNING after a completed five-minute bar.
  BUY and SELL are validated independently on their newest chronological
  holdout cases. A warning is suppressed unless its side has at least 30
  cases, accuracy of at least 55%, a 90% Wilson lower bound of at least 50%,
  and profit factor of at least 1.20 after configured costs. The warning does
  not place orders and cannot bypass the 30-minute action or event gates.
- Elliott is an independently gated confirmation and cannot rescue failed statistical evidence.
- Output is BUY, SELL, NO EDGE or BLOCKED.
- Version 9.3 writes only to `forecast_ledger_v90.sqlite`.

## Run

Copy all packaged files into the existing `gold_forecaster` folder, activate the environment, and run:

```powershell
python -m pip install -r requirements.txt
python -m py_compile app_v90.py gold_model_v90.py forecast_ledger_v90.py
python -m streamlit run app_v90.py --server.port 8503
```

Open `http://localhost:8503`. Version 8.2.5 may remain available separately on port 8502.
## Institutional factor status

- Prior highs/lows, equal-level tests, range compression, accumulation score
  and session VWAP (when volume exists) are calculated causally.
- POC, VAH and VAL activate only when the selected feed contains positive,
  verified traded volume. Spot tick counts are not silently treated as volume.
- The catalyst playbook requires at least 20 historical observations per event
  before it is marked qualified.
- CFTC/central-bank inputs use the optional release-timestamped CSV with
  columns `release_timestamp`, `gold_managed_money_net`, and/or
  `central_bank_demand_tonnes`. The timestamp must be the public release time,
  not the observation period, to prevent look-ahead leakage.
- Dark-pool and aggregated-liquidation factors remain disabled unless a
  licensed gold-relevant source and historical validation are supplied.

## Live settlement and out-of-sample reporting

- Each forecast is recorded before its result is known and settles against the
  first completed candle at or shortly after its 30-minute expiry.
- The live panel reports directional accuracy, Brier score, 80% interval
  coverage, median price error, calibration buckets and cost-aware results.
- Trading returns use a greedy non-overlapping 30-minute sample so repeated
  15-minute runs are not counted as independent simultaneous trades.
- The live gate remains `INSUFFICIENT` until 30 directional forecasts settle.
- Live performance and historical purged walk-forward performance are displayed
  separately and must never be combined into one accuracy number.
- Streamlit Community Cloud's local filesystem is not guaranteed to survive an
  app restart. Download the ledger regularly or configure persistent storage
  before treating it as a permanent audit record.

## API configuration

Only the existing Twelve Data market-data credential is required:

```toml
TWELVE_DATA_API_KEY = "your_key"
```

Never commit the credential to GitHub. Binance and Bybit are preferred public
perpetual feeds, BingX and Gate are transparent regional fallbacks, and OKX is
the third venue. These public snapshots require no API key and remain proxy
data rather than COMEX futures.
