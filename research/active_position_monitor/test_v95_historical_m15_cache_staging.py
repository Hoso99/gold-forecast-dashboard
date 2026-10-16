"""Offline cache tests; uses temporary directories, no API requests."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from v95_historical_m15_cache_staging import HistoricalM15Cache, BudgetExceeded

UTC = dt.timezone.utc


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = HistoricalM15Cache(Path(self.tmp.name) / "history.json",
                                        daily_limit=800, reserve=200)
        self.now = dt.datetime(2026, 10, 16, 14, 15, tzinfo=UTC)

    def test_oct16_complete_history_ready(self):
        start = dt.datetime(2026, 10, 16, 9, tzinfo=UTC)
        values = []
        for i in range(21):
            t = start + dt.timedelta(minutes=15*i)
            values.append({"datetime": t.strftime("%Y-%m-%d %H:%M:%S"),
                           "open": "4180", "high": "4182",
                           "low": "4178", "close": "4181"})
        status = self.cache.ingest(values, now=self.now, requested_candle_count=21)
        self.assertTrue(status["ready"])
        self.assertEqual(status["daily_candles_accounted"], 21)

    def test_budget_is_fail_closed(self):
        self.cache.ingest([{"datetime": "2026-10-16 13:45:00",
                            "open": "4180", "high": "4182",
                            "low": "4178", "close": "4181"}],
                          now=self.now, requested_candle_count=599)
        with self.assertRaises(BudgetExceeded):
            self.cache.ingest([{"datetime": "2026-10-16 14:00:00",
                                "open": "4180", "high": "4182",
                                "low": "4178", "close": "4181"}],
                              now=self.now, requested_candle_count=2)
        self.assertEqual(self.cache.status(now=self.now)["daily_candles_accounted"], 599)

    def test_duplicate_provider_candles_fail_without_accounting(self):
        item = {"datetime": "2026-10-16 13:45:00",
                "open": "4180", "high": "4182", "low": "4178", "close": "4181"}
        with self.assertRaises(ValueError):
            self.cache.ingest([item, item], now=self.now, requested_candle_count=2)
        self.assertEqual(self.cache.status(now=self.now)["daily_candles_accounted"], 0)


if __name__ == "__main__":
    unittest.main()
