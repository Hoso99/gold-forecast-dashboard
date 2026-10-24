import unittest
from datetime import datetime,timedelta
from research.v96_liquidity_sweep.trade_simulator import simulate_sell

class DeadlineRegressionTests(unittest.TestCase):
    def test_tp1_on_deadline_is_time_exit(self):
        start=datetime(2026,1,5,17,0)
        bars=[]
        for i in range(91):
            ts=(start+timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
            if i==90:
                o,h,l,c=100,100,99,99.5
            else:
                o,h,l,c=100,100.2,99.8,100
            bars.append({"minute_utc":ts,"o":o,"h":h,"l":l,"c":c})
        result=simulate_sell(bars,101)
        self.assertEqual(result.reason,"TIME")
        self.assertTrue(result.filled_tp1)
        self.assertAlmostEqual(result.gross_r,0.75)

if __name__=="__main__":
    unittest.main()
