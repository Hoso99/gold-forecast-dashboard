
import unittest
from unified_freshness import classify_freshness


ALL = [
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
]


class UnifiedFreshnessTests(unittest.TestCase):

    def classify(self, attempted, unavailable=(), cycle="cycle-002"):
        evidence = {
            "cycle_id": cycle,
            "attempted": list(attempted),
            "unavailable": list(unavailable),
        }
        return classify_freshness("cycle-002", evidence)

    def test_full_sell_evaluation(self):
        result = self.classify(ALL)
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")

    def test_before_diagnostics(self):
        result = self.classify(())
        self.assertEqual(result["diagnostics_freshness"], "STALE")

    def test_existing_position_partial(self):
        result = self.classify(ALL[:-1])
        self.assertEqual(result["diagnostics_freshness"], "PARTIAL")

    def test_optional_h4_failure_partial(self):
        result = self.classify(
            ALL,
            unavailable=("diagnostics", "research_votes"),
        )
        self.assertEqual(result["diagnostics_freshness"], "PARTIAL")

    def test_previous_cycle_unknown(self):
        result = self.classify(ALL, cycle="cycle-001")
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")

    def test_missing_evidence_unknown(self):
        result = classify_freshness("cycle-002", None)
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")

    def test_component_detail_preserved(self):
        result = self.classify(ALL[:-1])
        self.assertEqual(
            result["component_freshness"]["core_sell_detectors"],
            "NOT_RECALCULATED",
        )


if __name__ == "__main__":
    unittest.main()
