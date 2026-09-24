# Gold Version 8.3 — Calibrated Regime-Ensemble Challenger

Version 8.3 is separate from Version 8.2.5. It does not replace `app_v82.py` or `forecast_ledger_v825.sqlite` and contains no broker execution.

## Design

- Slow, release-timestamped macro variables classify the regime as BULLISH, BEARISH or NEUTRAL.
- Three diverse models form a calibrated next-hour ensemble.
- Every fold has a purged fit window, a separate calibration window and an untouched test window.
- Causal regime, normalized cross-asset shock and market-session features time the candidate.
- A robust jump detector compares each completed candle with a shifted 96-bar baseline, audits cross-asset co-shocks, and blocks release for four candles after an abnormal move.
- A technical-rejection engine waits for the four-bar cooldown, tests whether price reversed through the shock midpoint, and remains weightless until 30 holdout cases pass accuracy, Wilson-bound and profit-factor gates.
- The official Investing.com calendar widget displays three-star importance, previous, forecast and actual values. The user-confirmed three-star USD event checkbox blocks release within the next hour; widget data is not scraped or stored.
- Official release times are converted from U.S. Eastern time and displayed in GMT. After every model run, an event notice reports lockout, elevated preparation risk, or no scheduled high-impact event and names the relevant releases.
- Expected movement must exceed twice the configured trading cost.
- Evaluation uses every fourth 15-minute observation so one-hour outcomes do not overlap.
- Version 8.3 must beat Version 8.2.5 on ROC-AUC and Brier score or report NO EDGE.
- Elliott is an independently gated confirmation and cannot rescue failed statistical evidence.
- Output is BUY, SELL, NO EDGE or BLOCKED.
- Version 8.3 writes only to `forecast_ledger_v83.sqlite`.

## Run

Copy all packaged files into the existing `gold_forecaster` folder, activate the environment, and run:

```powershell
python -m pip install -r requirements.txt
python -m py_compile app_v83.py gold_model_v83.py forecast_ledger_v83.py
python -m streamlit run app_v83.py --server.port 8503
```

Open `http://localhost:8503`. Version 8.2.5 may remain available separately on port 8502.
# CME direct institutional feed

Version 8.3.0 can consume the licensed CME Real-Time Futures and Options
WebSocket feed for COMEX Gold (`GC`) trades and one-deep top of book.

1. Create a CME Group Login and OAuth API ID.
2. Ask CME Global Account Management to entitlement that API ID for the
   Real-Time Futures and Options WebSocket API and COMEX Gold.
3. Obtain an OAuth access token using CME's authorization workflow.
4. In Streamlit Cloud, open **Manage app → Settings → Secrets** and add:

```toml
CME_ACCESS_TOKEN = "your-short-lived-token"
```

Never commit the token to GitHub. CME access tokens expire and must be renewed.
The public app does not expose or persist the token.

Important: this WebSocket product provides trades and conflated one-deep top
of book. It is not Level 2. For multi-level depth, volume-at-price footprints,
order-level replenishment, or iceberg research, obtain the corresponding CME
MDP/Google Pub/Sub entitlement and historical data before enabling those
features in model decisions.

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
  first completed candle at or shortly after its one-hour expiry.
- The live panel reports directional accuracy, Brier score, 80% interval
  coverage, median price error, calibration buckets and cost-aware results.
- Trading returns use a greedy non-overlapping one-hour sample so repeated
  15-minute runs are not counted as independent simultaneous trades.
- The live gate remains `INSUFFICIENT` until 30 directional forecasts settle.
- Live performance and historical purged walk-forward performance are displayed
  separately and must never be combined into one accuracy number.
- Streamlit Community Cloud's local filesystem is not guaranteed to survive an
  app restart. Download the ledger regularly or configure persistent storage
  before treating it as a permanent audit record.
