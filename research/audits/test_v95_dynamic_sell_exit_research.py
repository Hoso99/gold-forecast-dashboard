"""Offline tests for the V9.5 hypothetical SELL exit decision state machine."""
import unittest
from v95_dynamic_sell_exit_research import SellExitEvidence, decide_sell_exit


class TestSellExitResearch(unittest.TestCase):
    def e(self, **changes):
        values = dict(entry=4100.0, initial_stop=4110.0,
                      current_stop=4110.0, price=4097.0)
        values.update(changes)
        return SellExitEvidence(**values)

    def test_hold(self):
        self.assertEqual(decide_sell_exit(self.e())["action"], "HOLD_SELL")

    def test_partial_at_one_r(self):
        self.assertEqual(decide_sell_exit(self.e(price=4090))["action"], "PARTIAL_EXIT")

    def test_no_retroactive_partial(self):
        result = decide_sell_exit(self.e(price=4090))
        self.assertNotIn("proposed_stop", result)

    def test_move_stop_only_after_acknowledged_partial(self):
        result = decide_sell_exit(self.e(price=4093, partial_already_taken=True))
        self.assertEqual(result["action"], "MOVE_SL")
        self.assertEqual(result["proposed_stop"], 4100.0)

    def test_never_widen(self):
        self.assertEqual(decide_sell_exit(self.e(current_stop=4111))["action"], "WAIT_DATA")

    def test_stop_precedes_reversal(self):
        self.assertEqual(decide_sell_exit(self.e(price=4110, completed_m15_bullish_invalidation=True))["action"], "SL_TOUCHED")

    def test_target(self):
        self.assertEqual(decide_sell_exit(self.e(price=4080))["action"], "TP_TOUCHED")

    def test_m15_invalidation(self):
        self.assertEqual(decide_sell_exit(self.e(completed_m15_bullish_invalidation=True))["action"], "EXIT_SELL_NOW")

    def test_m5_alone_does_not_exit(self):
        self.assertEqual(decide_sell_exit(self.e(completed_m5_reversal=True))["action"], "HOLD_SELL")

    def test_m5_and_h1_exit(self):
        self.assertEqual(decide_sell_exit(self.e(completed_m5_reversal=True, h1_bullish_confirmation=True))["action"], "EXIT_SELL_NOW")

    def test_event_alone_does_not_exit(self):
        self.assertEqual(decide_sell_exit(self.e(event_imminent=True))["action"], "HOLD_SELL")

    def test_stale_quote(self):
        self.assertEqual(decide_sell_exit(self.e(quote_fresh=False, price=4110))["action"], "WAIT_DATA")

    def test_no_broker_fill_claim(self):
        self.assertFalse(decide_sell_exit(self.e(price=4080))["broker_fill_confirmed"])


if __name__ == "__main__":
    unittest.main()
