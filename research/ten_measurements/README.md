# V9.4 ten-measurement research

Run `python research/ten_measurements/evaluate.py` against the repository's completed M1 collector data. The output `latest.json` records measurement statuses and inputs. The workflow is manual until the research branch is validated.

Implemented: (1) 10-minute candle close-location selling-pressure acceleration (proxy, not real order flow); (2) 20-minute high/low support/resistance (basic proxy); (3) bearish resistance-sweep candle pattern (not true liquidity); (4) completed M1/M5 bullish candle states; (5) completed M15/H1/H4 directional close comparisons when enough data; (6) M1 ATR14 and change; (10) active-trade pressure deterioration indicators without an actual position. Measurements 7 (calendar), 8 (spread/slippage) and 9 (DXY/yields) are explicitly unavailable until verified independent data sources are connected. No fake values or substitute proxies for missing external data.

This is a **diagnostic prototype**, not an entry/exit signal or validated predictive model. No live V9.4 logic, Telegram alerts, SL/TP or order execution are changed. Research comparisons and thresholds require forward testing. Market closures and missing bars can make longer-timeframe fields unavailable.
