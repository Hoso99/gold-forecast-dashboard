import unittest
from types import SimpleNamespace
import numpy as np
import pandas as pd

from gold_model_v83 import (
    _folds, _sigmoid_calibrate, classify_macro_regime, decide_v83,
    audit_technical_rejections, latest_shock_audit, shock_regime,
    technical_rejection_states,
    non_overlapping_evaluation,
)


class Version83Tests(unittest.TestCase):
    def test_vertical_move_triggers_shock_and_cooldown(self):
        index = pd.date_range("2026-01-01", periods=140, freq="15min", tz="UTC")
        close = np.linspace(2600, 2610, len(index))
        close[-1] += 45
        gold = pd.DataFrame({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close,
        }, index=index)
        audit = latest_shock_audit(gold)
        self.assertTrue(audit["active"])
        self.assertTrue(audit["detected_now"])
        self.assertGreaterEqual(audit["range_ratio"], 4)

    def test_shock_threshold_is_not_contaminated_by_current_bar(self):
        index = pd.date_range("2026-01-01", periods=140, freq="15min", tz="UTC")
        close = 2600 + np.sin(np.arange(len(index)) / 5)
        gold = pd.DataFrame({
            "open": close, "high": close + .5, "low": close - .5,
            "close": close,
        }, index=index)
        before = shock_regime(gold).iloc[-2].copy()
        altered = gold.copy()
        altered.iloc[-1, altered.columns.get_loc("close")] += 100
        altered.iloc[-1, altered.columns.get_loc("high")] += 100
        after = shock_regime(altered).iloc[-2]
        pd.testing.assert_series_equal(before, after)

    def test_upward_spike_rejection_requires_four_bar_confirmation(self):
        index = pd.date_range("2026-01-01", periods=150, freq="15min", tz="UTC")
        close = 2600 + np.sin(np.arange(len(index)) / 4)
        gold = pd.DataFrame({
            "open": close, "high": close + .5, "low": close - .5,
            "close": close,
        }, index=index)
        spike = 140
        gold.iloc[spike, gold.columns.get_loc("close")] += 45
        gold.iloc[spike, gold.columns.get_loc("high")] += 48
        states = technical_rejection_states(gold)
        self.assertEqual(states.rejection_signal.iloc[spike], 0)
        self.assertEqual(states.rejection_signal.iloc[spike + 4], -1)

    def test_small_rejection_sample_never_qualifies(self):
        index = pd.date_range("2026-01-01", periods=150, freq="15min", tz="UTC")
        close = np.linspace(2600, 2610, len(index))
        gold = pd.DataFrame({
            "open": close, "high": close + .5, "low": close - .5,
            "close": close,
        }, index=index)
        audit = audit_technical_rejections(gold)
        self.assertFalse(audit["qualified"])

    def test_walk_forward_folds_purge_the_forecast_horizon(self):
        for train, test in _folds(2400, 5, 4):
            self.assertGreaterEqual(test[0] - train[-1], 5)
            self.assertTrue(np.all(np.diff(train) == 1))
            self.assertTrue(np.all(np.diff(test) == 1))

    def test_fold_local_calibration_is_bounded_and_nonconstant(self):
        raw = np.linspace(.1, .9, 200)
        actual = (raw > .55).astype(int)
        calibrated = _sigmoid_calibrate(raw, actual, np.array([.2, .5, .8]))
        self.assertTrue(np.all((calibrated > 0) & (calibrated < 1)))
        self.assertLess(calibrated[0], calibrated[1])
        self.assertLess(calibrated[1], calibrated[2])

    def test_macro_regime_needs_mature_factors(self):
        index = pd.date_range("2026-01-01", periods=10, freq="D", tz="UTC")
        regime, score, reasons = classify_macro_regime(
            pd.DataFrame({"real_rate_pct": range(10)}, index=index), index[-1])
        self.assertEqual(regime, "NEUTRAL")
        self.assertEqual(score, 0)
        self.assertTrue(reasons)

    def test_non_overlapping_evaluation_uses_every_fourth_row(self):
        index = pd.date_range("2026-01-01", periods=40, freq="15min", tz="UTC")
        predictions = pd.DataFrame({
            "probability_up": [.7] * 40, "median": [.003] * 40,
            "actual_return": [.002] * 40,
        }, index=index)
        metrics = non_overlapping_evaluation(SimpleNamespace(predictions=predictions), .60, 10)
        self.assertEqual(metrics["Observations"], 10)
        self.assertEqual(metrics["Trades"], 10)

    def test_major_event_is_blocked(self):
        predictions = pd.DataFrame({
            "probability_up": [.7] * 100, "median": [.003] * 100,
            "actual_return": [.002] * 100})
        result = SimpleNamespace(
            predictions=predictions, probability_up=.7, median_return=.003,
            as_of=pd.Timestamp("2026-01-01", tz="UTC"),
            metrics={"ROC-AUC": .60, "Strategy total return": .1,
                     "Strategy max drawdown": -.02, "80% interval coverage": .8,
                     "Signal changes": 30},
            baseline_metrics={"ROC-AUC": .55})
        elliott = SimpleNamespace(probability_up=.7, qualified=False, current_bias="BUY")
        macro_index = pd.date_range("2025-01-01", periods=30, freq="D", tz="UTC")
        macro = pd.DataFrame({"real_rate_pct": np.linspace(2, 1, 30),
                              "dollar_index": np.linspace(110, 100, 30)}, index=macro_index)
        decision = decide_v83(result, macro, elliott, .60, 10, major_event=True)
        self.assertEqual(decision.action, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
