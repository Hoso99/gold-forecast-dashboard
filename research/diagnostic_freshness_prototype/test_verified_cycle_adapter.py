
import unittest
from diagnostic_freshness import enhance_verified_record


class VerifiedCycleAdapterTests(unittest.TestCase):

    def setUp(self):
        self.record = {
            "decision": "WAIT_SELL",
            "m1_bar_start_utc": "2026-10-23T03:00:00+00:00",
            "diagnostics": {"sell_pressure": 47.42},
            "research_votes": {"status": "AVAILABLE"},
            "core_sell_detectors": {"structural_sell": False},
            "shadow_entry": {"candidate_sell_evidence": False},
        }

    def classify(self, cycle_id, evidence):
        return enhance_verified_record(
            self.record,
            current_cycle_id=cycle_id,
            evidence=evidence,
        )

    def test_matching_completed_cycle_current(self):
        result = self.classify(
            "cycle-002",
            {
                "cycle_id": "cycle-002",
                "evaluation_stage": "AFTER_DIAGNOSTICS",
            },
        )
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")
        self.assertTrue(result["diagnostics_cycle_verified"])

    def test_previous_cycle_cannot_claim_current(self):
        result = self.classify(
            "cycle-002",
            {
                "cycle_id": "cycle-001",
                "evaluation_stage": "AFTER_DIAGNOSTICS",
            },
        )
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")
        self.assertFalse(result["diagnostics_cycle_verified"])

    def test_missing_evidence_unknown(self):
        result = self.classify("cycle-002", None)
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")

    def test_matching_blocked_cycle_stale(self):
        result = self.classify(
            "cycle-002",
            {
                "cycle_id": "cycle-002",
                "evaluation_stage": "BEFORE_DIAGNOSTICS",
            },
        )
        self.assertEqual(result["diagnostics_freshness"], "STALE")

    def test_invalid_stage_unknown(self):
        result = self.classify(
            "cycle-002",
            {
                "cycle_id": "cycle-002",
                "evaluation_stage": "INVALID",
            },
        )
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")

    def test_decision_unchanged(self):
        result = self.classify("cycle-002", None)
        self.assertEqual(result["decision"], "WAIT_SELL")


if __name__ == "__main__":
    unittest.main()
