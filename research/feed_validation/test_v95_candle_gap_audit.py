"""Tests for read-only V9.5 candle gap audit; no network or trading."""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from v95_candle_gap_audit import inspect, parse_minute, trading_minute

UTC = dt.timezone.utc


class CandleGapAuditTests(unittest.TestCase):
    def test_reject_naive_timestamp(self):
        with self.assertRaises(ValueError):
            parse_minute("2026-10-14T10:23:00")

    def test_ny_daily_break(self):
        self.assertFalse(trading_minute(dt.datetime(2026, 10, 14, 21, 30, tzinfo=UTC)))
        self.assertTrue(trading_minute(dt.datetime(2026, 10, 14, 22, 0, tzinfo=UTC)))

    def test_gap_and_database_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath = Path(folder) / "candles.sqlite3"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE candles (minute TEXT PRIMARY KEY)")
                db.executemany("INSERT INTO candles VALUES (?)", [
                    ("2026-10-14T10:22:00+00:00",),
                    ("2026-10-14T10:24:00+00:00",),
                ])
                db.commit()
            result = inspect(dbpath)
            self.assertEqual(result["missing"], ["2026-10-14T10:23:00+00:00"])
            self.assertEqual(result["count"], 1)
            with sqlite3.connect(dbpath) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 2)

    def test_maintenance_gap_is_not_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            dbpath = Path(folder) / "candles.sqlite3"
            with sqlite3.connect(dbpath) as db:
                db.execute("CREATE TABLE candles (minute TEXT PRIMARY KEY)")
                db.executemany("INSERT INTO candles VALUES (?)", [
                    ("2026-10-14T20:59:00+00:00",),
                    ("2026-10-14T22:00:00+00:00",),
                ])
                db.commit()
            self.assertEqual(inspect(dbpath)["count"], 0)


if __name__ == "__main__":
    unittest.main()
