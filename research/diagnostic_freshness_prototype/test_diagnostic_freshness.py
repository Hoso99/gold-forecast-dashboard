import unittest
from copy import deepcopy
from diagnostic_freshness import enhance_record, REQUIRED


class DiagnosticFreshnessTests(unittest.TestCase):

    def setUp(self):
        self.record = {
            "decision": "WAIT_SELL",
            "m1_bar_start_utc": "2026-10-23T03:00:00+00:00",
            "diagnostics": {"m1_sell_pressure_10": 47.42},
            "research_votes": {"status": "AVAILABLE"},
            "core_sell_detectors": {"structural_sell": False},
            "shadow_entry": {"candidate_sell_evidence": False},
        }

    def test_completed_evaluation_current(self):
        result = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")
        self.assertTrue(result["diagnostics_fresh"])

    def test_blocked_evaluation_stale(self):
        result = enhance_record(
            self.record,
            evaluation_stage="BEFORE_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "STALE")
        self.assertFalse(result["diagnostics_fresh"])

    def test_unavailable_component_partial(self):
        record = deepcopy(self.record)
        record["shadow_entry"] = {"status": "UNAVAILABLE"}
        result = enhance_record(
            record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "PARTIAL")

    def test_missing_component_partial(self):
        record = deepcopy(self.record)
        record.pop("research_votes")
        result = enhance_record(
            record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "PARTIAL")

    def test_unknown_stage_not_assumed_fresh(self):
        result = enhance_record(self.record)
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")
        self.assertFalse(result["diagnostics_fresh"])

    def test_original_record_unchanged(self):
        original = deepcopy(self.record)
        enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(self.record, original)

    def test_decision_preserved(self):
        result = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["decision"], "WAIT_SELL")

    def test_latest_candle_preserved(self):
        timestamp = "2026-10-23T03:01:00+00:00"
        result = enhance_record(
            self.record,
            timestamp,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["latest_available_m1_utc"], timestamp)

    def test_all_required_components_declared(self):
        self.assertEqual(len(REQUIRED), 4)


if __name__ == "__main__":
    unittest.main()
