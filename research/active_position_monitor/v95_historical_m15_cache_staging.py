"""Staging-only Twelve Data M15 cache and conservative daily candle budget.

No live monitor integration. Caller supplies a fetch function; the cache never
uses secrets, opens network connections, or changes live SQLite databases.
"""
import datetime as dt
import json
import os
from pathlib import Path

from v95_historical_recovery_staging import parse_twelve_data_m15, validate_indicator_window

UTC = dt.timezone.utc


class BudgetExceeded(RuntimeError):
    pass


class HistoricalM15Cache:
    def __init__(self, path, *, daily_limit=800, reserve=200):
        self.path = Path(path)
        if daily_limit <= 0 or reserve < 0 or reserve >= daily_limit:
            raise ValueError("invalid budget")
        self.daily_limit = daily_limit
        self.reserve = reserve

    def _read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {"candles": {}, "usage": {}}
        if not isinstance(data, dict) or not isinstance(data.get("candles"), dict) or not isinstance(data.get("usage"), dict):
            raise ValueError("invalid cache")
        return data

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def cached(self, *, now):
        data = self._read()
        return parse_twelve_data_m15(list(data["candles"].values()), now=now)

    def status(self, *, now):
        data = self._read()
        used = int(data["usage"].get(now.date().isoformat(), 0))
        bars = self.cached(now=now)
        ready, reason = validate_indicator_window(bars, now=now)
        return {"ready": ready, "reason": reason, "cached_bars": len(bars),
                "daily_candles_accounted": used,
                "remaining_research_budget": max(0, self.daily_limit - self.reserve - used)}

    def ingest(self, raw_values, *, now, requested_candle_count):
        """Account conservatively for ALL requested candles, not just returned rows.

        Caller must reserve before external API requests in any future integration;
        this staging method only validates already-obtained data. The usage count is
        a local accounting record, not a claim about Twelve Data provider credits.
        """
        if not isinstance(requested_candle_count, int) or requested_candle_count <= 0:
            raise ValueError("invalid requested candle count")
        data = self._read()
        day = now.date().isoformat()
        used = int(data["usage"].get(day, 0))
        if used + requested_candle_count > self.daily_limit - self.reserve:
            raise BudgetExceeded("historical candle research allowance exceeded")
        parsed = parse_twelve_data_m15(raw_values, now=now)
        if len(raw_values) > requested_candle_count:
            raise ValueError("provider returned more candles than accounted")
        for bar in parsed:
            key = bar["t"].isoformat()
            data["candles"][key] = {
                "datetime": key, "open": bar["o"], "high": bar["h"],
                "low": bar["l"], "close": bar["c"]
            }
        data["usage"][day] = used + requested_candle_count
        self._write(data)
        return self.status(now=now)
