
import unittest
from diagnostic_freshness import enhance_record


class EvaluationStageScenarioTests(unittest.TestCase):

    def setUp(self):
        self.record = {
            "decision": "WAIT_SELL",
            "m1_bar_start_utc": "2026-10-23T03:00:00+00:00",
            "diagnostics": {"sell_pressure": 47.42},
            "research_votes": {"status": "AVAILABLE"},
            "core_sell_detectors": {"structural_sell": False},
            "shadow_entry": {"candidate_sell_evidence": False},
        }

    def test_gate_rejection_before_diagnostics(self):
        record = dict(self.record, decision="WAIT_DATA")
        result = enhance_record(
            record,
            evaluation_stage="BEFORE_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "STALE")

    def test_wait_sell_after_diagnostics(self):
        result = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")

    def test_wait_data_after_diagnostics(self):
        record = dict(self.record, decision="WAIT_DATA")
        result = enhance_record(
            record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")
        self.assertEqual(result["decision"], "WAIT_DATA")

    def test_unavailable_diagnostics(self):
        record = dict(
            self.record,
            diagnostics={"status": "UNAVAILABLE"},
        )
        result = enhance_record(
            record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "PARTIAL")

    def test_unknown_historical_stage(self):
        result = enhance_record(self.record)
        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")
        self.assertFalse(result["diagnostics_fresh"])

    def test_trading_decision_preserved(self):
        for decision in (
            "WAIT_DATA",
            "WAIT_SELL",
            "NEWS_BLOCKED",
            "PAPER_SELL_ENTRY",
            "HOLD_SELL",
        ):
            with self.subTest(decision=decision):
                record = dict(self.record, decision=decision)
                result = enhance_record(
                    record,
                    evaluation_stage="AFTER_DIAGNOSTICS",
                )
                self.assertEqual(result["decision"], decision)


if __name__ == "__main__":
    unittest.main()
