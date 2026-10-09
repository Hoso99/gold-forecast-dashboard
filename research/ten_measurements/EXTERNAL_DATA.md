# Optional verified external data feeds

The ten-measurement evaluator accepts **optional** local CSV inputs:
```
python research/ten_measurements/evaluate.py \
  --events research/ten_measurements/inputs/events.csv \
  --quotes research/ten_measurements/inputs/quotes.csv \
  --macro research/ten_measurements/inputs/macro.csv
```

No live external provider has been connected yet. These CSVs are input contracts, **not synthetic data to fill missing fields**. If files are absent, the corresponding measurements remain UNAVAILABLE.

- `events.csv`: `event_time_utc,available_at_utc,event,importance`. Event time must be future relative to evaluation; `available_at_utc` must be the earliest time the calendar information was actually published/known. Importance HIGH or VERY_HIGH.
- `quotes.csv`: `observed_at_utc,bid,ask,source`. Valid bid <= ask, within 120 seconds of evaluation; spread is a quote snapshot, not guaranteed executable spread; slippage remains unknown.
- `macro.csv`: `available_at_utc,series,value,source`. Series `DXY` and `DGS10`; only observations available by evaluation time are used. DGS10 from FRED is **daily** and must never be represented as tick-level confirmation. Values without known publication/availability timestamps must not be used in retrospective decisions.

For reproducibility, preserve raw source payloads and original timestamps. Do not put API tokens or credentials in CSV or git. For economic calendar, prefer an approved Biquote source if authenticated data is available. A verified bid/ask quote must come from a provider with explicit bid/ask fields; M1 OHLC cannot substitute. A verified DXY feed is still required; do not use a generic USD proxy silently.

The 10-measurement diagnostic remains separate from live V9.4 and does not issue SELL/CLOSE SELL signals.
