import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v95_independent_sqlite_store import persist_validated_candle
from v95_independent_candle_builder import validate_ticks
from datetime import timedelta


class IsolatedSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "isolated_research.sqlite3"
        minute = datetime(2026, 10, 15, 8, 41, tzinfo=timezone.utc)
        ticks = [(minute + timedelta(seconds=s), 4000.0 + s / 100) for s in range(0, 60, 5)]
        self.candle = validate_ticks(minute, ticks, minute + timedelta(minutes=1))
        self.assertIsNotNone(self.candle)

    def test_insert_and_idempotent_repeat(self):
        self.assertEqual(persist_validated_candle(self.db, self.candle), "inserted")
        self.assertEqual(persist_validated_candle(self.db, self.candle), "duplicate")
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM independent_m1").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT source FROM independent_m1").fetchone()[0],
                             "biquote_independent_bid")

    def test_conflict_rejected_without_overwrite(self):
        persist_validated_candle(self.db, self.candle)
        conflict = dict(self.candle)
        conflict["high"] += 1
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            persist_validated_candle(self.db, conflict)

    def test_unvalidated_candle_rejected(self):
        invalid = dict(self.candle)
        invalid["research_only"] = False
        with self.assertRaises(ValueError):
            persist_validated_candle(self.db, invalid)
        self.assertFalse(self.db.exists())

    def test_reserved_primary_path_rejected(self):
        with self.assertRaises(ValueError):
            persist_validated_candle("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3",
                                     self.candle)

    def test_invalid_price_rejected(self):
        invalid = dict(self.candle)
        invalid["high"] = float("nan")
        with self.assertRaises(ValueError):
            persist_validated_candle(self.db, invalid)


if __name__ == "__main__":
    unittest.main()
