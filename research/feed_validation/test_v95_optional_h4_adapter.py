"""Offline tests for H4-optional research adapter."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "active_position_monitor"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from v95_optional_h4_adapter import evaluate_optional_h4

def bars(n, minutes):
    base = datetime(2026, 10, 14, tzinfo=timezone.utc)
    return [{"t": base + timedelta(minutes=i * minutes),
             "o": 4200.0-i, "h": 4201.0-i,
             "l": 4199.0-i, "c": 4199.5-i} for i in range(n)]

class H4AdapterTests(unittest.TestCase):
    def test_missing_h4_keeps_other_votes(self):
        info, result = evaluate_optional_h4(bars(100,1), bars(30,5),
                                            bars(30,15), bars(5,60), [])
        self.assertIsNone(info["h4_bearish"])
        self.assertIsNone(result["votes"]["trend"])
        self.assertIn("structure", result["votes"])
        self.assertIn("momentum", result["votes"])
        self.assertIn("candle_flow_proxy", result["votes"])
        self.assertEqual(result["agreement_available_votes"],
                         sum(result["votes"][k] for k in
                             ("structure", "momentum", "candle_flow_proxy")))
    def test_h4_present_uses_original_votes(self):
        info, result = evaluate_optional_h4(bars(100,1), bars(30,5),
                                            bars(30,15), bars(5,60), bars(3,240))
        self.assertIn("trend", result["votes"])
        self.assertEqual(result["status"], "RESEARCH_ONLY_UNVALIDATED")

if __name__ == "__main__":
    unittest.main()
