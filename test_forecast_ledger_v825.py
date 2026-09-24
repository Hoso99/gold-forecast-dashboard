import tempfile
import unittest
from pathlib import Path
import sqlite3

import pandas as pd

from forecast_ledger_v825 import ForecastLedger


class ForecastLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.ledger = ForecastLedger(Path(self.directory.name) / "ledger.sqlite")
        self.start = pd.Timestamp("2026-09-22 12:30", tz="UTC")

    def tearDown(self):
        self.directory.cleanup()

    def record(self, decision="BUY"):
        return self.ledger.record(
            model_version="8.2.5-test", data_timestamp=self.start,
            forecast_timestamp=self.start + pd.Timedelta(hours=1),
            starting_price=4340.0, directional_outlook="BUY", decision=decision,
            market_probability_up=.66, adjusted_probability_up=.67,
            lower_target=4330.0, median_target=4350.0, upper_target=4370.0,
            release_gate="PASS", gate_reasons="",
        )

    def test_repeated_run_does_not_duplicate_forecast(self):
        self.assertTrue(self.record())
        self.assertFalse(self.record())
        self.assertEqual(len(self.ledger.frame()), 1)

    def test_buy_forecast_settles_correctly(self):
        self.record("BUY")
        index = pd.date_range(self.start, periods=6, freq="15min")
        gold = pd.DataFrame({"close": [4340, 4342, 4344, 4346, 4352, 4353]}, index=index)
        self.assertEqual(self.ledger.settle(gold), 1)
        row = self.ledger.frame().iloc[0]
        self.assertEqual(row.status, "SETTLED")
        self.assertEqual(row.direction_result, "CORRECT")
        self.assertEqual(row.outlook_result, "CORRECT")
        self.assertEqual(row.actual_price, 4352.0)

    def test_wait_is_settled_but_not_scored(self):
        self.record("WAIT")
        index = pd.date_range(self.start, periods=5, freq="15min")
        gold = pd.DataFrame({"close": [4340, 4341, 4342, 4343, 4339]}, index=index)
        self.ledger.settle(gold)
        self.assertEqual(self.ledger.frame().iloc[0].direction_result, "NOT_SCORED")
        self.assertEqual(self.ledger.frame().iloc[0].outlook_result, "INCORRECT")

    def test_missing_expiry_candle_stays_pending(self):
        self.record("SELL")
        index = pd.date_range(self.start, periods=4, freq="15min")
        gold = pd.DataFrame({"close": [4340, 4339, 4338, 4337]}, index=index)
        self.assertEqual(self.ledger.settle(gold), 0)
        self.assertEqual(self.ledger.frame().iloc[0].status, "PENDING")

    def test_existing_ledger_schema_is_migrated(self):
        old_path = Path(self.directory.name) / "old.sqlite"
        with sqlite3.connect(old_path) as connection:
            connection.execute("""CREATE TABLE forecasts (
                forecast_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL,
                model_version TEXT NOT NULL, data_timestamp_utc TEXT NOT NULL,
                forecast_timestamp_utc TEXT NOT NULL, starting_price REAL NOT NULL,
                decision TEXT NOT NULL, market_probability_up REAL NOT NULL,
                adjusted_probability_up REAL NOT NULL, median_target REAL NOT NULL,
                release_gate TEXT NOT NULL, gate_reasons TEXT NOT NULL,
                status TEXT NOT NULL, actual_timestamp_utc TEXT, actual_price REAL,
                actual_return REAL, target_error REAL, direction_result TEXT)""")
        migrated = ForecastLedger(old_path)
        columns = set(migrated.frame().columns)
        self.assertIn("directional_outlook", columns)
        self.assertIn("lower_target", columns)
        self.assertIn("upper_target", columns)
        self.assertIn("outlook_result", columns)


if __name__ == "__main__":
    unittest.main()
