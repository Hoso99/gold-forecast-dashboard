
import unittest
from component_cycle_tracker import classify_cycle_components


class ComponentCycleTrackerTests(unittest.TestCase):

    def test_matching_full_cycle(self):
        evidence = {
            "cycle_id": "cycle-002",
            "attempted": [
                "diagnostics",
                "research_votes",
                "shadow_entry",
                "core_sell_detectors",
            ],
            "unavailable": [],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertTrue(
            all(v == "RECALCULATED" for v in result.values())
        )

    def test_previous_cycle_rejected(self):
        evidence = {
            "cycle_id": "cycle-001",
            "attempted": ["diagnostics"],
            "unavailable": [],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertTrue(
            all(v == "UNKNOWN" for v in result.values())
        )

    def test_partial_existing_position_cycle(self):
        evidence = {
            "cycle_id": "cycle-002",
            "attempted": [
                "diagnostics",
                "research_votes",
                "shadow_entry",
            ],
            "unavailable": [],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertEqual(
            result["core_sell_detectors"],
            "NOT_RECALCULATED",
        )

    def test_unavailable_optional_h4(self):
        evidence = {
            "cycle_id": "cycle-002",
            "attempted": [
                "diagnostics",
                "research_votes",
                "shadow_entry",
            ],
            "unavailable": [
                "diagnostics",
                "research_votes",
            ],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertEqual(
            result["diagnostics"],
            "UNAVAILABLE",
        )

    def test_invalid_evidence_rejected(self):
        evidence = {
            "cycle_id": "cycle-002",
            "attempted": ["invalid_component"],
            "unavailable": [],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertTrue(
            all(v == "UNKNOWN" for v in result.values())
        )

    def test_unattempted_unavailable_rejected(self):
        evidence = {
            "cycle_id": "cycle-002",
            "attempted": [],
            "unavailable": ["diagnostics"],
        }
        result = classify_cycle_components("cycle-002", evidence)
        self.assertTrue(
            all(v == "UNKNOWN" for v in result.values())
        )


if __name__ == "__main__":
    unittest.main()
