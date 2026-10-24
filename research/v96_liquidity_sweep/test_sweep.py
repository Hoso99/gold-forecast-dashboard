import unittest
from research.v96_liquidity_sweep.sweep import bearish_sweep, latest_confirmed_swing_high

class SweepTests(unittest.TestCase):
    def setUp(self):
        highs=[97,99,103,100,98,99]
        self.prior=[{"h":h,"l":h-3,"c":h-1} for h in highs]
    def test_confirmed_high(self):
        self.assertEqual(latest_confirmed_swing_high(self.prior)["price"],103)
    def test_rejection(self):
        self.assertIsNotNone(bearish_sweep(self.prior,{"h":104,"l":99,"c":102}))
    def test_no_close_back_below(self):
        self.assertIsNone(bearish_sweep(self.prior,{"h":104,"l":99,"c":103.5}))
    def test_no_sweep(self):
        self.assertIsNone(bearish_sweep(self.prior,{"h":102,"l":99,"c":100}))
    def test_no_future_confirmation(self):
        self.assertIsNone(bearish_sweep(self.prior[:4],{"h":104,"l":99,"c":102}))

if __name__=="__main__":
    unittest.main()
