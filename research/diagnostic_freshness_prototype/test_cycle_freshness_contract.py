
import unittest
from diagnostic_freshness import enhance_record


class CycleFreshnessContractTests(unittest.TestCase):

    def setUp(self):
        self.record = {
            "decision": "WAIT_SELL",
            "m1_bar_start_utc": "2026-10-23T03:00:00+00:00",
            "diagnostics": {"sell_pressure": 47.42},
            "research_votes": {"status": "AVAILABLE"},
            "core_sell_detectors": {"structural_sell": False},
            "shadow_entry": {"candidate_sell_evidence": False},
        }

    def test_current_cycle_completed(self):
        result = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        self.assertEqual(result["diagnostics_freshness"], "CURRENT")

    def test_new_cycle_without_stage_is_unknown(self):
        previous = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        next_record = dict(previous, decision="WAIT_DATA")

        result = enhance_record(next_record)

        self.assertEqual(result["diagnostics_freshness"], "UNKNOWN")
        self.assertFalse(result["diagnostics_fresh"])

    def test_new_cycle_explicitly_blocked_is_stale(self):
        previous = enhance_record(
            self.record,
            evaluation_stage="AFTER_DIAGNOSTICS",
        )
        next_record = dict(previous, decision="WAIT_DATA")

        result = enhance_record(
            next_record,
            evaluation_stage="BEFORE_DIAGNOSTICS",
        )

        self.assertEqual(result["diagnostics_freshness"], "STALE")
        self.assertFalse(result["diagnostics_fresh"])


if __name__ == "__main__":
    unittest.main()
