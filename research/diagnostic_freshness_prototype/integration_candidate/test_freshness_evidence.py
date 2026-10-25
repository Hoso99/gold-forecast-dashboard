
import unittest
from freshness_evidence import FreshnessEvidence


class FreshnessEvidenceTests(unittest.TestCase):

    def test_new_cycles_are_distinct(self):
        self.assertNotEqual(
            FreshnessEvidence().cycle_id,
            FreshnessEvidence().cycle_id,
        )

    def test_new_cycle_is_empty(self):
        evidence = FreshnessEvidence()
        self.assertEqual(evidence.snapshot()["attempted"], [])

    def test_completed_component(self):
        evidence = FreshnessEvidence()
        evidence.mark_completed("diagnostics")
        self.assertEqual(
            evidence.snapshot()["attempted"],
            ["diagnostics"],
        )

    def test_unavailable_component(self):
        evidence = FreshnessEvidence()
        evidence.mark_unavailable("shadow_entry")
        self.assertEqual(
            evidence.snapshot()["unavailable"],
            ["shadow_entry"],
        )

    def test_failure_not_completed(self):
        evidence = FreshnessEvidence()
        evidence.mark_completed("diagnostics")
        evidence.mark_unavailable("diagnostics")
        self.assertNotIn("diagnostics", evidence.completed)

    def test_unknown_component_rejected(self):
        evidence = FreshnessEvidence()
        with self.assertRaises(ValueError):
            evidence.mark_completed("unknown_component")


if __name__ == "__main__":
    unittest.main()
