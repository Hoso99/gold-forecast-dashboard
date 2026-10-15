"""No-price coverage tests; not historical Biquote data validation."""
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).with_name("v95_outage_continuity_sim.py")
spec = importlib.util.spec_from_file_location("continuity_sim", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ContinuityTests(unittest.TestCase):
    def test_three_historical_slots_with_backup_online(self):
        result = mod.continuity([], mod.OUTAGES)
        self.assertEqual((result["passed"], result["total"]), (3, 3))
        self.assertTrue(all(x["independent_present"] for x in result["results"]))

    def test_primary_down_and_backup_down_is_not_fixed(self):
        result = mod.continuity([], [])
        self.assertEqual(result["passed"], 0)
        self.assertTrue(all(not x["continuity_possible"] for x in result["results"]))

    def test_one_backup_gap_is_reported_not_hidden(self):
        result = mod.continuity([], mod.OUTAGES[:2])
        self.assertEqual(result["passed"], 2)
        self.assertFalse(result["results"][2]["continuity_possible"])

    def test_no_non_utc_timestamps(self):
        with self.assertRaises(ValueError):
            mod.continuity([], ["2026-10-14T10:23:00+03:00"])


if __name__ == "__main__":
    unittest.main()
