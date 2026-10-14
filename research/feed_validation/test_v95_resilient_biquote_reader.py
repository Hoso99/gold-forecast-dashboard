"""Offline regression tests for gap-tolerant Biquote M1 reader."""
import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from v95_resilient_biquote_reader import read_candles

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "candles.sqlite3"
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE candles (minute TEXT PRIMARY KEY, open REAL, high REAL, low REAL, close REAL)")
            db.executemany("INSERT INTO candles VALUES (?,?,?,?,?)", [
                ((START + dt.timedelta(minutes=i)).isoformat(), 100.0, 101.0, 99.0, 100.5)
                for i in range(40) if i not in (4, 5, 20)
            ])
        self.now = START + dt.timedelta(minutes=41)

    def test_multiple_missing_minutes_do_not_block_reader(self):
        rows = read_candles(self.path, now=self.now)
        self.assertEqual(len(rows), 37)
        self.assertEqual(rows[-1]["t"], START + dt.timedelta(minutes=39))

    def test_database_is_never_written(self):
        before = self.path.read_bytes()
        read_candles(self.path, now=self.now)
        self.assertEqual(self.path.read_bytes(), before)

    def test_stale_latest_candle_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "stale"):
            read_candles(self.path, now=self.now + dt.timedelta(minutes=5))

    def test_invalid_ohlc_is_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE candles SET low=102 WHERE minute=?", (START.isoformat(),))
        with self.assertRaisesRegex(RuntimeError, "invalid"):
            read_candles(self.path, now=self.now)


if __name__ == "__main__":
    unittest.main()
