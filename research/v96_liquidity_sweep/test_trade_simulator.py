import unittest
from datetime import datetime, timedelta
from research.v96_liquidity_sweep.trade_simulator import simulate_sell

def bars(prices):
    start=datetime(2026,1,5,13,0)
    return [{"minute_utc":(start+timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
             "o":o,"h":h,"l":l,"c":c}
            for i,(o,h,l,c) in enumerate(prices)]

class TradeSimulatorTests(unittest.TestCase):
    def test_initial_stop_wins_ambiguous_bar(self):
        x=simulate_sell(bars([(100,102,98,99)]),101)
        self.assertEqual((x.reason,x.gross_r),("INITIAL_STOP",-1.0))
    def test_both_targets_require_separate_bars(self):
        x=simulate_sell(bars([(100,100,99,99.5),(99.5,99.5,98,98)]),101)
        self.assertEqual((x.reason,x.gross_r),("TP2",1.5))
    def test_tp1_then_break_even(self):
        x=simulate_sell(bars([(100,100,99,99.5),(99.5,100,99,100)]),101)
        self.assertEqual((x.reason,x.gross_r),("BREAKEVEN",0.5))
    def test_cost_deducted(self):
        x=simulate_sell(bars([(100,101,99,100)]),101,cost_per_oz=0.2)
        self.assertAlmostEqual(x.net_r,-1.2)
    def test_unresolved(self):
        self.assertIsNone(simulate_sell(bars([(100,100.5,99.8,100)]),101))
    def test_gap_not_credited(self):
        data=bars([(100,100.2,99.8,100),(100,100.2,99.8,100)])
        data[1]["minute_utc"]="2026-01-05 13:03:00"
        self.assertIsNone(simulate_sell(data,101))
    def test_stop_gap_slippage(self):
        x=simulate_sell(bars([(102,103,101,102)]),101)
        self.assertIsNone(x) # entry above precomputed stop: invalid setup

if __name__=="__main__":
    unittest.main()
