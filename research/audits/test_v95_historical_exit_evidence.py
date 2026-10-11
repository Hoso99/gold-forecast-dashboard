"""Causal evidence checks: future M1 candles cannot affect an earlier decision."""
import unittest
import pandas as pd
from v95_historical_exit_evidence import evidence_at


class TestHistoricalExitEvidence(unittest.TestCase):
    def setUp(self):
        ix=pd.date_range("2026-10-08T00:00:00Z",periods=241,freq="min")
        close=[4100-0.02*i for i in range(len(ix))]
        self.m=pd.DataFrame({"open":close,"high":[x+0.1 for x in close],
                             "low":[x-0.1 for x in close],"close":close},index=ix)
        self.t=pd.Timestamp("2026-10-08T04:00:00Z")
        self.kw=dict(entry=4100.0,initial_stop=4110.0,current_stop=4110.0)

    def test_completed_candles_only(self):
        first=evidence_at(self.m,self.t,**self.kw)
        altered=self.m.copy()
        altered.loc[altered.index>=self.t,["open","high","low","close"]]=9999
        second=evidence_at(altered,self.t,**self.kw)
        self.assertEqual(first,second)
        self.assertEqual(first["data_scope"],"COMPLETED_BARS_ONLY_RESEARCH")

    def test_missing_latest_bar_fails_closed(self):
        m=self.m.drop(self.t-pd.Timedelta(minutes=1))
        self.assertEqual(evidence_at(m,self.t,**self.kw)["action"],"WAIT_DATA")

    def test_duplicate_timestamp_rejected(self):
        m=pd.concat([self.m,self.m.iloc[[-1]]])
        with self.assertRaises(ValueError):
            evidence_at(m,self.t,**self.kw)

    def test_incomplete_prior_hour_fails_closed(self):
        m=self.m.drop(self.t-pd.Timedelta(minutes=23))
        self.assertEqual(evidence_at(m,self.t,**self.kw)["action"],"WAIT_DATA")


if __name__=="__main__":
    unittest.main()
