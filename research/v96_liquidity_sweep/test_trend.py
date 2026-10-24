import unittest
from research.v96_liquidity_sweep.trend import ema, bearish_trend, h1_h4_bearish

class TrendTests(unittest.TestCase):
    def test_ema_requires_history(self):
        self.assertIsNone(ema([1,2,3],9))
    def test_falling_series(self):
        bars=[{"c":float(100-i)} for i in range(30)]
        self.assertTrue(bearish_trend(bars))
        self.assertTrue(h1_h4_bearish(bars,bars))
    def test_rising_series(self):
        bars=[{"c":float(100+i)} for i in range(30)]
        self.assertFalse(bearish_trend(bars))
        self.assertFalse(h1_h4_bearish(bars,bars))
    def test_no_confirmation_on_flat_last_close(self):
        bars=[{"c":float(100-i)} for i in range(30)]
        bars[-1]["c"]=bars[-2]["c"]
        self.assertFalse(bearish_trend(bars))

if __name__=="__main__":
    unittest.main()
