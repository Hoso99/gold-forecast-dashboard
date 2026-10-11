"""V9.5 exit engine safety tests, discovered by existing research CI."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from v95_exit_variant_engine import simulate_sell,variants


class TestV95ExitVariants(unittest.TestCase):
    def test_stop_before_target_on_same_bar(self):
        b=[dict(open=100,high=104,low=90,close=95)]
        for mode in ("baseline","fixed","partial_fixed","partial_chandelier","chandelier"):
            v=simulate_sell(b,100,103,atr_m5=1,mode=mode)
            self.assertEqual(v["outcome"],"STOP",mode)
            self.assertLess(v["net_r"],-1,mode)

    def test_gap_through_stop_is_adverse(self):
        b=[dict(open=105,high=106,low=104,close=105)]
        v=simulate_sell(b,100,103,atr_m5=1)
        self.assertAlmostEqual(v["net_r"],(-5-.30)/3)

    def test_partial_target_remainder(self):
        b=[dict(open=100,high=100.5,low=97,close=98),
           dict(open=98,high=99,low=93,close=94)]
        v=simulate_sell(b,100,103,atr_m5=1,mode="partial_fixed")
        self.assertEqual(v["outcome"],"TARGET")
        self.assertAlmostEqual(v["net_r"],(1.5+3-.30)/3)

    def test_no_widen_stop_after_partial(self):
        b=[dict(open=100,high=101,low=96,close=97,
                atr_m5_closed=2,m5_close_completed=True),
           dict(open=97,high=100.5,low=96.5,close=99)]
        v=simulate_sell(b,100,103,atr_m5=2,mode="partial_chandelier")
        self.assertEqual(v["outcome"],"STOP")
        self.assertTrue(v["partial"])

    def test_predeclared_variants(self):
        a=variants()
        self.assertEqual(len(a),31)
        self.assertEqual(len({x["name"] for x in a}),31)


if __name__=="__main__":
    unittest.main()
