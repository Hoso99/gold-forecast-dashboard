
import unittest


def verified_stage(current_cycle_id, evidence):
    """Isolated design contract; not connected to the running monitor."""
    if not isinstance(evidence, dict):
        return None

    if not current_cycle_id:
        return None

    if evidence.get("cycle_id") != current_cycle_id:
        return None

    stage = evidence.get("evaluation_stage")
    if stage not in ("BEFORE_DIAGNOSTICS", "AFTER_DIAGNOSTICS"):
        return None

    return stage


class CycleEvidenceTests(unittest.TestCase):

    def test_matching_cycle(self):
        evidence = {
            "cycle_id": "cycle-002",
            "evaluation_stage": "AFTER_DIAGNOSTICS",
        }
        self.assertEqual(
            verified_stage("cycle-002", evidence),
            "AFTER_DIAGNOSTICS",
        )

    def test_previous_cycle_rejected(self):
        evidence = {
            "cycle_id": "cycle-001",
            "evaluation_stage": "AFTER_DIAGNOSTICS",
        }
        self.assertIsNone(verified_stage("cycle-002", evidence))

    def test_missing_cycle_rejected(self):
        evidence = {"evaluation_stage": "AFTER_DIAGNOSTICS"}
        self.assertIsNone(verified_stage("cycle-002", evidence))

    def test_invalid_stage_rejected(self):
        evidence = {
            "cycle_id": "cycle-002",
            "evaluation_stage": "UNKNOWN_STAGE",
        }
        self.assertIsNone(verified_stage("cycle-002", evidence))

    def test_missing_evidence_rejected(self):
        self.assertIsNone(verified_stage("cycle-002", None))


if __name__ == "__main__":
    unittest.main()
