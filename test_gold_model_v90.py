import unittest

import numpy as np
import pandas as pd

from gold_model_v90 import (
    _calibration_weights, _conformalize_quantiles, selective_reliability)


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


if __name__ == "__main__":
    unittest.main()
