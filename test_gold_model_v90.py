import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from gold_model_v90 import (
    _calibration_weights, _conformalize_quantiles,
    _side_reversal_validation, combined_directional_lean,
    five_minute_reversal_states, institutional_liquidity_score,
    selective_reliability,
    short_term_technical_trend)


class Version90AccuracyTests(unittest.TestCase):
    def test_calibration_weights_favour_better_member(self):
        actual = np.array([0, 0, 1, 1])
        probabilities = np.column_stack([
            [.05, .10, .90, .95],
            [.45, .55, .45, .55],
            [.80, .70, .30, .20],
        ])
        weights = _calibration_weights(probabilities, actual)
        self.assertAlmostEqual(float(weights.sum()), 1.0)
        self.assertGreater(weights[0], weights[1])
        self.assertGreater(weights[1], weights[2])

    def test_conformal_interval_expands_for_misses(self):
        actual = np.array([-.03, -.01, .01, .03])
        lower = np.array([-.01] * 4)
        median = np.zeros(4)
        upper = np.array([.01] * 4)
        adjusted = _conformalize_quantiles(
            actual, lower, median, upper, [-.01], [0], [.01])
        self.assertLess(adjusted[0][0], -.01)
        self.assertGreater(adjusted[2][0], .01)

    def test_selective_gate_uses_only_current_side(self):
        predictions = pd.DataFrame({
            "probability_up": [.70] * 30 + [.30] * 30,
            "actual_up": [1] * 25 + [0] * 5 + [0] * 25 + [1] * 5,
        })
        buy = selective_reliability(predictions, .70, .60)
        sell = selective_reliability(predictions, .30, .60)
        self.assertEqual(buy["observations"], 30)
        self.assertEqual(sell["observations"], 30)
        self.assertTrue(buy["qualified"])
        self.assertTrue(sell["qualified"])

    def test_short_term_trend_detects_rising_and_falling_prices(self):
        index = pd.date_range("2026-01-01", periods=100, freq="15min", tz="UTC")
        rising = np.linspace(2600, 2660, len(index))
        def frame(close):
            return pd.DataFrame({
                "open": np.r_[close[0], close[:-1]],
                "high": close + .5, "low": close - .5, "close": close,
            }, index=index)
        self.assertEqual(short_term_technical_trend(frame(rising))["trend"],
                         "UPTREND")
        self.assertEqual(short_term_technical_trend(frame(rising[::-1]))["trend"],
                         "DOWNTREND")

    def test_combined_lean_reports_direction_without_claiming_action(self):
        result = SimpleNamespace(
            probability_up=.70, median_return=.003,
            as_of=pd.Timestamp("2026-01-01", tz="UTC"))
        technical = {"trend": "UPTREND", "score": .70}
        consensus = SimpleNamespace(
            agreement=3, direction="BUY PRESSURE")
        lean = combined_directional_lean(
            result, pd.DataFrame(), technical, consensus)
        self.assertEqual(lean["lean"], "BUY LEAN")
        self.assertFalse(lean["actionable"])

    def test_institutional_liquidity_proxy_is_small_and_directional(self):
        high = SimpleNamespace(
            nearest_liquidity="PRIOR HIGH", liquidity_distance_pct=.002,
            compression_percentile=.60)
        low = SimpleNamespace(
            nearest_liquidity="PRIOR LOW", liquidity_distance_pct=.002,
            compression_percentile=.60)
        far = SimpleNamespace(
            nearest_liquidity="PRIOR HIGH", liquidity_distance_pct=.02,
            compression_percentile=.60)
        self.assertGreater(institutional_liquidity_score(high), 0)
        self.assertLess(institutional_liquidity_score(low), 0)
        self.assertEqual(institutional_liquidity_score(far), 0)

    def test_five_minute_detector_flags_exhaustion_break(self):
        n = 140
        index = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
        close = 2600 + np.sin(np.arange(n) / 4) * .3
        close[-13:-1] = np.linspace(2600, 2610, 12)
        close[-1] = 2607
        open_ = np.r_[close[0], close[:-1]]
        frame = pd.DataFrame({
            "open": open_, "high": np.maximum(open_, close) + .3,
            "low": np.minimum(open_, close) - .3, "close": close,
        }, index=index)
        frame.iloc[-1, frame.columns.get_loc("high")] = 2610.2
        frame.iloc[-1, frame.columns.get_loc("low")] = 2606.5
        states = five_minute_reversal_states(frame)
        self.assertEqual(states.signal.iloc[-1], -1)

    def test_reversal_validation_requires_holdout_skill(self):
        sample = pd.DataFrame({
            "signal": [-1] * 30,
            "future_return": [-.003] * 27 + [.003] * 3,
        })
        result = _side_reversal_validation(sample, -1, 10, 30)
        self.assertTrue(result["qualified"])
        self.assertGreaterEqual(result["lower_bound"], .50)


if __name__ == "__main__":
    unittest.main()
