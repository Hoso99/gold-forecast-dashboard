"""Research-only smoke and causality-shape checks for V9.5 M5 warning study.

Discovered by existing research workflow test_v94_*.py pattern.
"""
import importlib.util
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("v95_m5_reversal_warning_study",HERE/"v95_m5_reversal_warning_study.py")
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)


class TestV95M5WarningResearch(unittest.TestCase):
    def test_reversal_warning_historical_study(self):
        result=module.study()
        self.assertEqual(result["status"],"EXPLORATORY_NOT_LIVE")
        self.assertEqual(result["warning_delay_minutes"],15)
        self.assertEqual(result["timestamp_semantics"],"UNVERIFIED_OPEN_STAMP_ASSUMPTION")
        for period in ("development","holdout"):
            self.assertIn(period,result["periods"])
            groups=result["periods"][period]
            self.assertIn("warning",groups)
            self.assertIn("no_warning",groups)
            self.assertGreater(groups["warning"]["n"]+groups["no_warning"]["n"],0)
        print("V95_M5_WARNING_STUDY_RESULT",__import__("json").dumps(result,sort_keys=True))


if __name__=="__main__":
    unittest.main()
