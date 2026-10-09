import csv,tempfile,unittest
from pathlib import Path
from stratify_sell import analyze
class StratifyTests(unittest.TestCase):
 def test_sell_only_and_support_threshold(self):
  with tempfile.TemporaryDirectory() as d:
   source=Path(d)/"source.csv";target=Path(d)/"out.csv"
   fields=["m15_signal","horizon_minutes","h1_trend","m5_bullish","atr14_m1","distance_to_support","forward_close_change","sell_favorable_move","sell_adverse_move"]
   with source.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    w.writerow(dict(zip(fields,["SELL",15,"DOWN","False",2,1,-2,3,1])))
    w.writerow(dict(zip(fields,["WAIT",15,"UP","True",2,1,4,0,4])))
   result=analyze(source,target)
   self.assertEqual(result["sell_rows"],1)
   with target.open() as f: rows=list(csv.DictReader(f))
   self.assertTrue(any(r["dimension"]=="support_within_1_atr" and r["group"]=="True" for r in rows))
   self.assertTrue(all(int(r["n"])==1 for r in rows))
if __name__=="__main__":unittest.main()
