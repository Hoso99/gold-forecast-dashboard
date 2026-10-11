"""Offline V9.5 trade replay tests, discovered by research CI."""
import importlib.util
import sys
import unittest
from pathlib import Path

P=Path(__file__).resolve().parent
sys.path.insert(0,str(P))
spec=importlib.util.spec_from_file_location("v95_sell_sltp_replay",P/"v95_sell_sltp_replay.py")
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


class TestV95SellSLTP(unittest.TestCase):
    def test_stop_first_when_both_hit(self):
        import pandas as pd
        f=pd.DataFrame([{"open":100,"high":105,"low":94,"close":99}])
        result=mod.resolve_sell(100,103,96,f,0.30)
        self.assertEqual(result["outcome"],"STOP")
        self.assertLess(result["net_r"],-1)

    def test_target_with_cost(self):
        import pandas as pd
        f=pd.DataFrame([{"open":100,"high":101,"low":93,"close":95}])
        result=mod.resolve_sell(100,103,94,f,0.30)
        self.assertEqual(result["outcome"],"TARGET")
        self.assertAlmostEqual(result["net_r"],1.9)

    def test_replay_research_only(self):
        result=mod.replay()
        self.assertEqual(result["status"],"EXPLORATORY_NOT_LIVE")
        self.assertEqual(result["timestamp_semantics"],"UNVERIFIED_OPEN_STAMP_ASSUMPTION")
        self.assertEqual(result["same_bar_resolution"],"STOP_FIRST")
        for period in ("development","holdout"):
            for group in ("M15","M15_plus_M5"):
                self.assertIn("n",result["periods"][period][group])
        print("V95_SLTP_REPLAY_RESULT",__import__("json").dumps(result,sort_keys=True))


if __name__=="__main__":
    unittest.main()
