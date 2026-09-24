# XAU/USD Multi-Horizon Forecast Lab

A research dashboard for forecasting spot-gold direction and price ranges over
1, 5, 21, 63, and 252 trading days. It downloads daily market data, constructs
macro/technical features, performs leakage-aware walk-forward testing, and
produces probability-based signals.

## What it provides

- Probability that gold finishes higher at each horizon
- Median forecast and 80% prediction interval
- BUY / NEUTRAL / SELL research signal
- Expanding-window, out-of-sample backtest
- Baseline comparison, Brier score, ROC-AUC, accuracy, and interval coverage
- Feature-importance and equity-curve views

This is a decision-support tool, not investment advice. Forecasts are uncertain,
Yahoo Finance symbols are convenient research proxies, and the daily series may
not match an executable broker quote. Do not trade from this project without
independent validation, better institutional data, slippage modeling, and paper
trading.

## Setup in VS Code (Windows)

Open this folder in VS Code, then open **Terminal > New Terminal** and run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

If PowerShell blocks activation, run this once in that terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

The browser should open automatically. The first model run can take several
minutes because every displayed result is generated out of sample.

## Data design

The target is `GC=F` adjusted close, used as a liquid daily gold proxy. Inputs
include gold trend/momentum/volatility, silver (`SI=F`), the US dollar (`DX-Y.NYB`),
Treasuries (`TLT`), inflation-linked bonds (`TIP`), oil (`CL=F`), equities (`SPY`),
and volatility (`^VIX`). All inputs are aligned to gold trading dates, forward
filled only, and every training split is separated from its test split by the
forecast horizon.

Yahoo occasionally changes or omits symbols. The downloader tolerates missing
cross-market series and displays what was actually used.

## Interpretation

- **Probability** is model-estimated, not certainty.
- **Price range** is an empirical 80% interval; inspect its measured coverage.
- **BUY/SELL** requires probability beyond the selected threshold and expected
  movement larger than the estimated round-trip cost.
- **Backtest return** uses non-overlapping forecast decisions to avoid counting
  overlapping positions as independent trades.
- A useful model should beat the baseline across multiple walk-forward periods,
  remain calibrated, and survive higher assumed costs.

## Files

- `app.py` — Streamlit interface
- `gold_model.py` — download, features, modeling, metrics, and signals
- `tests/test_gold_model.py` — offline tests for core calculations

## Run tests

```powershell
python -m unittest discover -s tests -v
```

