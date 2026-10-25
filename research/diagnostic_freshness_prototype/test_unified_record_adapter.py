
import unittest
from unified_record_adapter import enhance_unified_record


ALL = [
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
]


class UnifiedRecordAdapterTests(unittest.TestCase):

    def setUp(self):
        self.record = {
            "decision": "HOLD_SELL",
            "m1_bar_start_utc": "2026-10-23T03:00:00+00:00",
            "diagnostics": {"sell_pressure": 47.42},
            "research_votes": {"status": "AVAILABLE"},
            "shadow_entry": {"candidate_sell_evidence": False},
            "core_sell_detectors": {"structural_sell": False},
        }

    def classify(self, attempted, cycle="cycle-002"):
        return enhance_unified_record(
            self.record,
            current_cycle_id="cycle-002",
            evidence={
                "cycle_id": cycle,
                "attempted": list(attempted),
                "unavailable": [],
            },
        )

    def test_partial_position_not_current(self):
        result = self.classify(ALL[:-1])
        self.assertEqual(
            result["diagnostics_freshness"], "PARTIAL"
        )
        self.assertFalse(result["diagnostics_fresh"])

    def test_full_evaluation_current(self):
        result = self.classify(ALL)
        self.assertEqual(
            result["diagnostics_freshness"], "CURRENT"
        )
        self.assertTrue(result["diagnostics_fresh"])

    def test_previous_cycle_unknown(self):
        result = self.classify(ALL, cycle="cycle-001")
        self.assertEqual(
            result["diagnostics_freshness"], "UNKNOWN"
        )

    def test_decision_preserved(self):
        result = self.classify(ALL[:-1])
        self.assertEqual(result["decision"], "HOLD_SELL")

    def test_original_record_unchanged(self):
        before = dict(self.record)
        self.classify(ALL[:-1])
        self.assertEqual(self.record, before)

    def test_component_detail(self):
        result = self.classify(ALL[:-1])
        self.assertEqual(
            result["component_freshness"]["core_sell_detectors"],
            "NOT_RECALCULATED",
        )


if __name__ == "__main__":
    unittest.main()
