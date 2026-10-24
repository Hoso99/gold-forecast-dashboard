import unittest
from research.v96_liquidity_sweep.signal_pipeline import SweepMSS

class PipelineTests(unittest.TestCase):
    def test_sweep_then_mss_on_later_bar(self):
        pipe=SweepMSS()
        highs=[97,99,103,100,98,99,100,101]
        lows=[94,95,96,94,90,94,95,96]
        for h,l in zip(highs,lows):
            pipe.update({"h":h,"l":l,"c":(h+l)/2})
        sweep=pipe.update({"h":104,"l":99,"c":102})
        self.assertEqual(sweep["event"],"SWEEP")
        self.assertEqual(pipe.update({"h":102,"l":89,"c":89})["event"],"SELL_CONFIRMED")

    def test_no_same_bar_mss(self):
        pipe=SweepMSS()
        highs=[97,99,103,100,98,99,100,101]
        lows=[94,95,96,94,90,94,95,96]
        for h,l in zip(highs,lows):
            pipe.update({"h":h,"l":l,"c":(h+l)/2})
        result=pipe.update({"h":104,"l":88,"c":89})
        self.assertNotEqual(result["event"],"SELL_CONFIRMED")

if __name__=="__main__":
    unittest.main()
