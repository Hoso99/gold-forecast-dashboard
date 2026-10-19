"""Pure unit tests for V9.5 PAPER-only SELL gate attribution."""
import unittest
from v95_sell_gate_attribution_research import diagnose_sell_gate


class AttributionTests(unittest.TestCase):
    def test_location_only_veto(self):
        x = diagnose_sell_gate(structural_sell=True, h1_bearish=True,
            m5_bearish=True, support_buffer=False, sell_power=82.4,
            price=4153.1, older_support=4155, m15_atr=5)
        self.assertEqual(x["decision"], "WAIT_SELL")
        self.assertEqual(x["failed_gates"], ["support_buffer"])
        self.assertTrue(x["location_only_veto"])
        self.assertTrue(x["counterfactual_without_location"])

    def test_unknown_structural_gate_cannot_be_assumed_true(self):
        x = diagnose_sell_gate(structural_sell=False, h1_bearish=True,
            m5_bearish=True, support_buffer=False, sell_power=82.4)
        self.assertFalse(x["location_only_veto"])
        self.assertEqual(x["failed_gates"], ["structural_sell", "support_buffer"])

    def test_power_gate_also_fails(self):
        x = diagnose_sell_gate(structural_sell=True, h1_bearish=True,
            m5_bearish=True, support_buffer=False, sell_power=59.9)
        self.assertFalse(x["counterfactual_without_location"])

    def test_all_gates_pass(self):
        x = diagnose_sell_gate(structural_sell=True, h1_bearish=True,
            m5_bearish=True, support_buffer=True, sell_power=60.0)
        self.assertEqual(x["decision"], "QUALIFIED_TECHNICAL_SELL")
        self.assertFalse(x["location_only_veto"])

    def test_m5_rejection_even_with_location(self):
        x = diagnose_sell_gate(structural_sell=True, h1_bearish=True,
            m5_bearish=False, support_buffer=True, sell_power=90)
        self.assertEqual(x["failed_gates"], ["m5_bearish"])

    def test_atr_distance_is_optional(self):
        x = diagnose_sell_gate(structural_sell=True, h1_bearish=True,
            m5_bearish=True, support_buffer=False, sell_power=90,
            price=4150, older_support=4140, m15_atr=0)
        self.assertIsNone(x["distance_above_support_atr"])


if __name__ == "__main__":
    unittest.main()
