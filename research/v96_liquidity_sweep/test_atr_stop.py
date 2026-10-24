import unittest
from research.v96_liquidity_sweep.atr_stop import atr, sell_stop

class ATRStopTests(unittest.TestCase):
    def test_requires_completed_history(self):
        self.assertIsNone(atr([{"h":102,"l":99,"c":100}]*14))
    def test_constant_true_range(self):
        bars=[{"h":101,"l":99,"c":100} for _ in range(16)]
        self.assertAlmostEqual(atr(bars),2.0)
    def test_sweep_high_dominates(self):
        self.assertEqual(sell_stop(100,104,2),106)
    def test_atr_dominates(self):
        self.assertEqual(sell_stop(100,100,4),106)
    def test_wide_stop_rejected_not_clamped(self):
        self.assertIsNone(sell_stop(100,110,2,max_distance=8))
    def test_two_atr_comparison(self):
        self.assertEqual(sell_stop(100,100,4,atr_multiple=2),108)

if __name__=="__main__":
    unittest.main()
