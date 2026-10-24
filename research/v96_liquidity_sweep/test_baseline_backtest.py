import unittest
from research.v96_liquidity_sweep.baseline_backtest import evaluate

class BaselineTests(unittest.TestCase):
    def test_empty(self):
        result=evaluate([])
        self.assertEqual(result["closed_trades"],0)
        self.assertIsNone(result["mean_net_r"])
        self.assertIn("BASELINE",result["warning"])
    def test_no_signal(self):
        rows=[{"minute_utc":f"2026-01-05 13:{i:02d}:00",
               "o":100.0,"h":100.5,"l":99.5,"c":100.0}
              for i in range(10)]
        result=evaluate(rows)
        self.assertEqual(result["closed_trades"],0)
        self.assertEqual(result["counts"].get("mss",0),0)

if __name__=="__main__":
    unittest.main()
