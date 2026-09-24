import tempfile
import unittest
from pathlib import Path

import pandas as pd

from forecast_ledger_v83 import ForecastLedgerV83


class ForecastLedgerV83PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = ForecastLedgerV83(Path(self.temp.name) / "ledger.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def _record(self, i, probability=.70, decision="BUY"):
        start = pd.Timestamp("2026-01-05 10:00", tz="UTC") + pd.Timedelta(hours=i)
        self.ledger.record(
            model_version="8.3-test", data_timestamp=start,
            forecast_timestamp=start + pd.Timedelta(hours=1),
            starting_price=2600, directional_outlook="BUY", decision=decision,
            market_probability_up=probability, adjusted_probability_up=probability,
            lower_target=2590, median_target=2605, upper_target=2620,
            release_gate="PASS", gate_reasons="")

    def test_live_metrics_use_only_settled_forecasts(self):
        self._record(0)
        self._record(1)
        index = pd.date_range("2026-01-05 11:00", periods=1, freq="15min", tz="UTC")
        self.ledger.settle(pd.DataFrame({"close": [2610]}, index=index))
        metrics = self.ledger.live_performance()
        self.assertEqual(metrics["settled"], 1)
        self.assertEqual(metrics["direction_accuracy"], 1.0)
        self.assertEqual(metrics["status"], "INSUFFICIENT")

    def test_calibration_uses_recorded_probability(self):
        self._record(0, probability=.70)
        index = pd.date_range("2026-01-05 11:00", periods=1, freq="15min", tz="UTC")
        self.ledger.settle(pd.DataFrame({"close": [2610]}, index=index))
        table = self.ledger.calibration_table()
        self.assertEqual(int(table.iloc[0]["Forecasts"]), 1)
        self.assertAlmostEqual(table.iloc[0]["Observed up frequency"], 1.0)


if __name__ == "__main__":
    unittest.main()
