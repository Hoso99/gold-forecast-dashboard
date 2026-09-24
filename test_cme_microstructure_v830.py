import unittest
import pandas as pd

from cme_microstructure_v830 import (
    audit_microstructure, normalize_messages, subscription_message)


class CMEMicrostructureTests(unittest.TestCase):
    def test_gc_subscription_is_explicit(self):
        request = subscription_message()
        self.assertEqual(request["payload"]["subscriptions"][0]["productCode"], "GC")
        self.assertIn("TOB", request["payload"]["subscriptionMessageTypes"])

    def test_normalizes_trade_and_top_book(self):
        messages = [{"header": {"messageType": "TOB", "sentTime": "2026-09-24T12:00:00Z"},
                     "payload": [{"instrument": {"symbol": "GCZ6"},
                                  "bidLevel": [{"price": "4268.0", "quantity": "30"}],
                                  "askLevel": [{"price": "4268.1", "quantity": "10"}]}]},
                    {"header": {"messageType": "TRD", "sentTime": "2026-09-24T12:00:01Z"},
                     "payload": [{"instrument": {"symbol": "GCZ6"},
                                  "tradeSummary": {"tradePrice": "4268.1",
                                                   "tradeQty": "5",
                                                   "aggressorSide": "BUY"}}]}]
        frame = normalize_messages(messages)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.iloc[0].bid_size, 30)
        audit = audit_microstructure(frame, now=pd.Timestamp("2026-09-24T12:00:05Z"))
        self.assertEqual(audit.status, "LIVE")
        self.assertAlmostEqual(audit.top_imbalance, .5)
        self.assertEqual(audit.signed_volume_delta, 5)

    def test_empty_feed_fails_closed(self):
        audit = audit_microstructure(pd.DataFrame())
        self.assertEqual(audit.status, "UNAVAILABLE")
        self.assertEqual(audit.risk, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
