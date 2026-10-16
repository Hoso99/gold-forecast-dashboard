"""Synthetic regression tests; no private data, no live services."""
import unittest
from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config

def bar(o,c,h=None,l=None):
    return {"o":o,"c":c,"h":max(o,c) if h is None else h,"l":min(o,c) if l is None else l}

class HybridCChecks(unittest.TestCase):
    def test_protective_stop_precedence(self):
        c=HybridC()
        c.open_initial(100,110,80)
        for _ in range(10): c.on_completed_m1(bar(100,100))
        result=c.on_completed_m1(bar(100,109,111,99))
        self.assertEqual(result["action"],"PROTECTIVE_SL")
        self.assertIsNotNone(c.position)

    def test_both_protective_touches_are_ambiguous(self):
        c=HybridC()
        c.open_initial(100,110,80)
        for _ in range(10): c.on_completed_m1(bar(100,100))
        self.assertEqual(c.on_completed_m1(bar(100,100,111,79))["action"],
                         "INCONCLUSIVE_SL_TP_ORDER")

    def test_false_reversal_votes_cancel_exit(self):
        c=HybridC()
        c.open_initial(100,120,60)
        # Build neutral candles, then a completed bullish breakout.
        for _ in range(11): c.on_completed_m1(bar(100,100,101,99))
        c.on_completed_m1(bar(100,105,105,100))
        self.assertIsNotNone(c.reversal_anchor)
        # Force causal detector to see a rapid buying-power collapse and
        # a close below the resistance; never require future bars.
        c.reversal_peak_buy=100
        result=c.on_completed_m1(bar(104,99,104,99))
        self.assertEqual(result["action"],"FALSE_REVERSAL_HOLD")
        self.assertTrue(result["lost_bullish_structure"])
        self.assertTrue(result["buy_power_drop"])

    def test_exit_confirmation_opens_fifteen_minute_window(self):
        c=HybridC()
        c.open_initial(100,110,80)
        c.confirm_paper_exit()
        self.assertEqual(c.reentry_left,15)
        self.assertIsNone(c.position)

    def test_no_reentry_without_window(self):
        c=HybridC()
        with self.assertRaises(ValueError):
            c.confirm_paper_reentry(100,110,80)

if __name__=="__main__":
    unittest.main()
