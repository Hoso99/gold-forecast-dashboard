"""Descriptive stratification of SELL indications; not parameter optimization or live signals."""
import argparse,csv,json
from collections import defaultdict
from pathlib import Path

def analyze(input_csv,output_csv):
    with open(input_csv,newline="") as f: rows=list(csv.DictReader(f))
    groups=defaultdict(list)
    for r in rows:
        if r.get("m15_signal")!="SELL": continue
        # Descriptive, fixed categories; do not tune on this small sample.
        horizon=int(r["horizon_minutes"])
        h1=r.get("h1_trend","")
        bullish=r.get("m5_bullish","")
        atr=float(r["atr14_m1"]) if r.get("atr14_m1") else None
        support=float(r["distance_to_support"]) if r.get("distance_to_support") else None
        near=(support is not None and atr is not None and atr>0 and support/atr<=1.0)
        for dimension,value in [("all","SELL"),("h1_trend",h1),
                                ("m5_bullish",bullish),
                                ("support_within_1_atr",str(near))]:
            groups[(horizon,dimension,value)].append(r)
    result=[]
    for (horizon,dimension,value),subset in sorted(groups.items()):
        changes=[float(r["forward_close_change"]) for r in subset]
        result.append({"horizon_minutes":horizon,"dimension":dimension,"group":value,
            "n":len(subset),"avg_forward_change":round(sum(changes)/len(changes),5),
            "lower_close_fraction":round(sum(x<0 for x in changes)/len(changes),4),
            "mean_favorable":round(sum(float(r["sell_favorable_move"]) for r in subset)/len(subset),5),
            "mean_adverse":round(sum(float(r["sell_adverse_move"]) for r in subset)/len(subset),5),
            "warning":"DESCRIPTIVE_ONLY_SMALL_OVERLAPPING_SAMPLE"})
    p=Path(output_csv);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",newline="") as f:
        columns=["horizon_minutes","dimension","group","n","avg_forward_change",
                 "lower_close_fraction","mean_favorable","mean_adverse","warning"]
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(result)
    return {"sell_rows":sum(r.get("m15_signal")=="SELL" for r in rows),
            "groups":len(result),"output":str(p)}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps(analyze(a.input,a.output)))
