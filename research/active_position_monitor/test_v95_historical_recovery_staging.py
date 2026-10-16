"""Offline regression checks for staging-only M15 recovery. No API calls."""
import datetime as dt
import unittest

from v95_historical_recovery_staging import (
    parse_twelve_data_m15, validate_indicator_window, compare_sources
)

UTC = dt.timezone.utc


def candle(t, close=4180.0):
    return {"t": t, "o": close, "h": close + 2, "l": close - 2, "c": close}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 10, 16, 14, 15, tzinfo=UTC)
        start = dt.datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
        self.bars = [candle(start + dt.timedelta(minutes=15 * i)) for i in range(21)]

    def test_complete_historical_window(self):
        self.assertEqual(validate_indicator_window(self.bars, now=self.now), (True, "READY"))

    def test_oct16_missing_three_biquote_buckets(self):
        gaps = {(9, 15), (12, 15), (12, 30)}
        incomplete = [x for x in self.bars if (x["t"].hour, x["t"].minute) not in gaps]
        allowed, reason = validate_indicator_window(incomplete, now=self.now)
        self.assertFalse(allowed)
        self.assertIn("gap", reason)

    def test_no_silent_cross_provider_splice(self):
        td = [dict(x) for x in self.bars]
        td[15] = dict(td[15], c=4175.0)
        allowed, reason, _ = compare_sources(self.bars, td)
        self.assertFalse(allowed)
        self.assertIn("discrepancy", reason)

    def test_incomplete_bar_is_excluded(self):
        raw = [{"datetime": "2026-10-16 14:15:00",
                "open": "4180", "high": "4182", "low": "4178", "close": "4181"}]
        self.assertEqual(parse_twelve_data_m15(raw, now=self.now), [])

    def test_duplicate_bars_rejected(self):
        raw = [{"datetime": "2026-10-16 13:45:00",
                "open": "4180", "high": "4182", "low": "4178", "close": "4181"}] * 2
        with self.assertRaises(ValueError):
            parse_twelve_data_m15(raw, now=self.now)


if __name__ == "__main__":
    unittest.main()
