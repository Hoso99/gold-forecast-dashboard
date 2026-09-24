import unittest
import numpy as np
import pandas as pd

from institutional_features_v830 import (
    catalyst_playbook, institutional_features, latest_institutional_audit,
    volume_profile)


def market(rows=500, volume=True):
    index = pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC")
    close = 2600 + np.sin(np.arange(rows) / 15) * 3
    data = {"open": close, "high": close + .5, "low": close - .5,
            "close": close}
    if volume:
        data["volume"] = 100 + np.arange(rows) % 20
    return pd.DataFrame(data, index=index)


class InstitutionalFeatureTests(unittest.TestCase):
    def test_features_are_causal(self):
        gold = market()
        before = institutional_features(gold).iloc[-2].copy()
        changed = gold.copy()
        changed.iloc[-1, changed.columns.get_loc("close")] += 100
        after = institutional_features(changed).iloc[-2]
        pd.testing.assert_series_equal(before, after)

    def test_volume_profile_requires_real_volume(self):
        self.assertEqual(volume_profile(market(volume=False))["status"], "UNAVAILABLE")
        self.assertEqual(volume_profile(market())["status"], "AVAILABLE")

    def test_audit_labels_liquidity_as_proxy(self):
        audit = latest_institutional_audit(market())
        self.assertTrue(any("proxy" in reason for reason in audit.reasons))

    def test_playbook_never_qualifies_small_sample(self):
        gold = market()
        events = pd.DataFrame({"timestamp": gold.index[[100, 200]],
                               "event": ["CPI", "CPI"]})
        result = catalyst_playbook(gold, events)
        self.assertEqual(result.iloc[0].Cases, 2)
        self.assertFalse(bool(result.iloc[0].Qualified))


if __name__ == "__main__":
    unittest.main()
