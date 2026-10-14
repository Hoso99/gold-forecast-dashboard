"""Offline tests for the read-only V9.5 recovery candidate inspector."""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from v95_recovery_dry_run import candidate, inspect, market_minute, parse_utc

UTC = dt.timezone.utc
TARGET = dt.datetime(2026, 10, 14, 10, 23, tzinfo=UTC)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "candles.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE candles (minute TEXT PRIMARY KEY, open REAL, high REAL, low REAL, close REAL, ticks INTEGER)")
            db.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?)", [
                ("2026-10-14T10:22:00+00:00", 4090, 4092, 4089, 4091, 50),
                ("2026-10-14T10:24:00+00:00", 4092, 4094, 4091, 4093, 60)])
    def tearDown(self):
        self.temp.cleanup()
    def test_no_write(self):
        self.assertEqual(inspect(self.db, TARGET)["status"], "AWAITING_PROVIDER_CANDIDATE")
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 2)
    def test_candidate_quarantined(self):
        payload = {"values": [{"datetime": "2026-10-14 10:23:00", "open": "4091",
                               "high": "4094", "low": "4090", "close": "4092"}]}
        self.assertEqual(inspect(self.db, TARGET, payload)["decision"],
                         "REVIEW_REQUIRED_NO_AUTOMATIC_MERGE")
    def test_invalid(self):
        with self.assertRaises(ValueError):
            candidate({"values": [{"datetime": "2026-10-14 10:23:00", "open": "5",
                                   "high": "3", "low": "4", "close": "6"}]}, TARGET)
    def test_duplicate(self):
        row = {"datetime": "2026-10-14 10:23:00", "open": "1",
               "high": "2", "low": "1", "close": "2"}
        with self.assertRaises(ValueError):
            candidate({"values": [row, row]}, TARGET)
    def test_session(self):
        self.assertFalse(market_minute(dt.datetime(2026, 10, 14, 21, 30, tzinfo=UTC)))
        self.assertTrue(market_minute(TARGET))
    def test_naive_timestamp(self):
        with self.assertRaises(ValueError):
            parse_utc("2026-10-14T10:23:00")


if __name__ == "__main__":
    unittest.main()
