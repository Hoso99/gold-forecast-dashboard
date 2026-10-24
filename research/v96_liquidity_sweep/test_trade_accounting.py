import unittest
from research.v96_liquidity_sweep.trade_accounting import gross_r


class TradeAccountingTests(unittest.TestCase):
    def test_initial_stop(self):
        self.assertEqual(gross_r(False, False, True), -1.0)

    def test_first_target_then_break_even(self):
        self.assertEqual(gross_r(True, False, False), 0.5)

    def test_both_targets(self):
        self.assertEqual(gross_r(True, True, False), 1.5)

    def test_unresolved(self):
        self.assertIsNone(gross_r(False, False, False))

    def test_impossible_sequence(self):
        with self.assertRaises(ValueError):
            gross_r(False, True, False)


if __name__ == "__main__":
    unittest.main()
