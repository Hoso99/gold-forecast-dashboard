"""V9.4 XAU/USD candle-dynamics research (research only; live V9.4 unchanged)."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

SYMBOL="XAU/USD"; M1_TARGET=int(os.getenv("DYNAMICS_M1_BARS","225000")); BATCH_SIZE=min(int(os.getenv("DYNAMICS_BATCH_SIZE","5000")),5000)
PAUSE=float(os.getenv("DYNAMICS_REQUEST_PAUSE","10")); CYPRUS=ZoneInfo("Europe/Nicosia"); FOLLOW=(15,30,60,120,240)
OUT=Path("candle_dynamics_m15_v94.csv")

def fetch(params):
    with urlopen("https://api.twelvedata.com/time_series?"+urlencode(params),timeout=30) as r: return json.loads(r.read().decode())

def download(api):
    batches=[]; remaining=M1_TARGET; end=None
    while remaining>0:
        size=min(BATCH_SIZE,remaining); p={"symbol":SYMBOL,"interval":"1min","outputsize":size,"timezone":"UTC","format":"JSON","apikey":api}
        if end is not None: p["end_date"]=end.strftime("%Y-%m-%d %H:%M:%S")
        x=fetch(p)
        if x.get("status")=="error": raise RuntimeError("Twelve Data: "+str(x.get("message")))
        if not x.get("values"): break
        d=pd.DataFrame(x["values"]); d["datetime"]=pd.to_datetime(d["datetime"],utc=True,errors="coerce")
        for c in ["open","high","low","close"]: d[c]=pd.to_numeric(d[c],errors="coerce")
        d=d.set_index("datetime").sort_index()[["open","high","low","close"]].dropna()
        if d.empty: break
        batches.append(d); end=d.index[0]-pd.Timedelta(minutes=1); remaining-=len(d)
        print(f"Downloaded {len(d)} M1; oldest={d.index[0]}; remaining={remaining}")
        if len(d)<size: break
        if remaining>0: time.sleep(PAUSE)
    if not batches: raise RuntimeError("No M1 data downloaded")
    z=pd.concat(batches); return z[~z.index.duplicated(keep="last")].sort_index().tail(M1_TARGET)

def session(h):
    return "ASIA_00_07" if h<7 else "EUROPE_07_12" if h<12 else "EU_US_12_17" if h<17 else "US_LATE_17_22" if h<22 else "LATE_22_24"

def reconstruct(m1):
    w=m1.copy(); w["bucket"]=w.index.floor("15min"); rows=[]
    for t,g in w.groupby("bucket",sort=True):
        g=g.sort_index()
        if len(g)!=15: continue
        o=float(g.open.iloc[0]); h=float(g.high.max()); l=float(g.low.min()); c=float(g.close.iloc[-1]); body=c-o; rng=h-l
        mv=g.close.astype(float).diff().dropna(); signs=np.sign(mv.to_numpy()); nz=signs[signs!=0]; changes=int(np.sum(nz[1:]!=nz[:-1])) if len(nz)>1 else 0
        travel=float(mv.abs().sum()); seg=[]
        for s in (0,5,10):
            q=g.iloc[s:s+5]; m=q.close.astype(float).diff().dropna(); seg.append((float(q.close.iloc[-1]-q.open.iloc[0]),float(abs(m[m<0].sum())),float(m[m>0].sum()),float(m.abs().sum())))
        ht=g.high.idxmax(); lt=g.low.idxmin(); seq="HIGH_FIRST" if ht<lt else "LOW_FIRST" if lt<ht else "SAME_MINUTE_AMBIGUOUS"
        rev=[]; a=g.close.astype(float).to_numpy(); last=0; leg=a[0]; prev=a[0]
        for v in a[1:]:
            s=np.sign(v-prev)
            if s!=0:
                if last!=0 and s!=last: rev.append(abs(prev-leg)); leg=prev
                last=s
            prev=v
        cy=t.tz_convert(CYPRUS)
        rows.append(dict(model_time=t,cyprus_time=cy,utc_hour=t.hour,cyprus_hour=cy.hour,session_utc=session(t.hour),open=o,high=h,low=l,close=c,body=body,body_abs=abs(body),range=rng,upper_wick=h-max(o,c),lower_wick=min(o,c)-l,up_moves=int((mv>0).sum()),down_moves=int((mv<0).sum()),flat_moves=int((mv==0).sum()),direction_changes=changes,total_travel=travel,directional_efficiency=abs(body)/travel if travel else np.nan,early_net_1_5=seg[0][0],middle_net_6_10=seg[1][0],late_net_11_15=seg[2][0],early_sell=seg[0][1],middle_sell=seg[1][1],late_sell=seg[2][1],early_buy=seg[0][2],middle_buy=seg[1][2],late_buy=seg[2][2],early_travel=seg[0][3],middle_travel=seg[1][3],late_travel=seg[2][3],sell_acceleration_to_close=seg[2][1]-seg[0][1],buy_acceleration_to_close=seg[2][2]-seg[0][2],high_low_sequence=seq,high_minute=int((ht-t).total_seconds()//60)+1,low_minute=int((lt-t).total_seconds()//60)+1,avg_reversal_size=float(np.mean(rev)) if rev else 0,max_reversal_size=float(np.max(rev)) if rev else 0,event_regime="UNKNOWN"))
    if not rows: raise RuntimeError("No complete M15 groups reconstructed")
    return pd.DataFrame(rows).set_index("model_time").sort_index()

def enrich(d):
    d=d.copy(); pc=d.close.shift(1); tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1); d["atr14"]=tr.rolling(14).mean(); d["range_atr_ratio"]=d.range/d.atr14
    q33=d.range_atr_ratio.rolling(200,min_periods=50).quantile(.33); q67=d.range_atr_ratio.rolling(200,min_periods=50).quantile(.67); d["volatility_regime"]=np.where(d.range_atr_ratio<=q33,"QUIET",np.where(d.range_atr_ratio>=q67,"HIGH","NORMAL"))
    ph=d.high.shift(1); pl=d.low.shift(1); d["break_prev_high"]=d.high>ph; d["break_prev_low"]=d.low<pl; d["high_break_continuation"]=d.close>ph; d["high_break_rejection"]=d.break_prev_high&(d.close<=ph); d["low_break_continuation"]=d.close<pl; d["low_break_rejection"]=d.break_prev_low&(d.close>=pl)
    d["resistance_48"]=d.high.shift(1).rolling(48).max(); d["support_48"]=d.low.shift(1).rolling(48).min(); d["distance_to_resistance_atr"]=(d.resistance_48-d.close)/d.atr14; d["distance_to_support_atr"]=(d.close-d.support_48)/d.atr14
    d["bearish_candidate"]=(d.body<0)&(d.late_sell>d.late_buy)&(d.sell_acceleration_to_close>0); d["bullish_candidate"]=(d.body>0)&(d.late_buy>d.late_sell)&(d.buy_acceleration_to_close>0)
    for mins in FOLLOW:
        n=mins//15; d[f"forward_{mins}m"]=d.close.shift(-n)-d.close; lows=pd.concat([d.low.shift(-k) for k in range(1,n+1)],axis=1).min(axis=1); highs=pd.concat([d.high.shift(-k) for k in range(1,n+1)],axis=1).max(axis=1); d[f"sell_mfe_{mins}m"]=d.close-lows; d[f"sell_mae_{mins}m"]=highs-d.close
    d["false_sell_60m"]=d.bearish_candidate&(d.forward_60m>0); return d

def summaries(d):
    t=d.assign(large_move=d.range_atr_ratio>=1.25).groupby(["utc_hour","session_utc"]).agg(candles=("close","size"),avg_range=("range","mean"),avg_range_atr=("range_atr_ratio","mean"),large_move_rate=("large_move","mean"),avg_sell_accel=("sell_acceleration_to_close","mean"),bearish_candidate_rate=("bearish_candidate","mean"),avg_forward_60m=("forward_60m","mean")).reset_index()
    rows=[]
    for reg in ["QUIET","NORMAL","HIGH"]:
        g=d[d.volatility_regime==reg]
        for name,mask in [("BEARISH_CANDIDATE",g.bearish_candidate),("BULLISH_CANDIDATE",g.bullish_candidate),("LOW_BREAK_REJECTION",g.low_break_rejection),("HIGH_BREAK_REJECTION",g.high_break_rejection)]:
            x=g[mask]; rows.append(dict(volatility_regime=reg,pattern=name,count=len(x),avg_efficiency=x.directional_efficiency.mean(),avg_forward_15m=x.forward_15m.mean(),avg_forward_30m=x.forward_30m.mean(),avg_forward_60m=x.forward_60m.mean(),avg_forward_120m=x.forward_120m.mean(),avg_sell_mfe_60m=x.sell_mfe_60m.mean(),avg_sell_mae_60m=x.sell_mae_60m.mean()))
    p=pd.DataFrame(rows); f=[]
    for name,mask in [("ALL",pd.Series(True,index=d.index)),("BEARISH_CANDIDATE",d.bearish_candidate),("FALSE_SELL_60M",d.false_sell_60m),("HIGH_FIRST",d.high_low_sequence.eq("HIGH_FIRST")),("LOW_FIRST",d.high_low_sequence.eq("LOW_FIRST"))]:
        g=d[mask]; row={"group":name,"count":len(g)}
        for mins in FOLLOW: row[f"avg_forward_{mins}m"]=g[f"forward_{mins}m"].mean(); row[f"avg_sell_mfe_{mins}m"]=g[f"sell_mfe_{mins}m"].mean(); row[f"avg_sell_mae_{mins}m"]=g[f"sell_mae_{mins}m"].mean()
        f.append(row)
    return t,p,pd.DataFrame(f)

def detailed_intracandle_analysis(d):
    """Compare early/middle/late M15 dynamics and false-SELL behaviour."""

    x = d.copy()

    # Direction of each 5-minute section
    x["phase_1_dir"] = np.sign(x["seg1_net"])
    x["phase_2_dir"] = np.sign(x["seg2_net"])
    x["phase_3_dir"] = np.sign(x["seg3_net"])

    # Absolute movement during each section
    x["phase_1_move"] = x["seg1_net"].abs()
    x["phase_2_move"] = x["seg2_net"].abs()
    x["phase_3_move"] = x["seg3_net"].abs()

    # Selling acceleration toward M15 close
    x["late_sell_acceleration"] = (
        (-x["seg3_net"]) - (-x["seg1_net"])
    )

    # Which third contained the largest net movement
    phase_moves = x[
        ["phase_1_move", "phase_2_move", "phase_3_move"]
    ]

    x["dominant_phase"] = (
        phase_moves.idxmax(axis=1)
        .str.replace("phase_", "", regex=False)
        .str.replace("_move", "", regex=False)
    )

    # Path classification
    x["path_type"] = "MIXED"

    x.loc[
        (x["seg1_net"] < 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "SELL_ALL_3"

    x.loc[
        (x["seg1_net"] >= 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "LATE_SELL"

    x.loc[
        (x["seg1_net"] < 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] >= 0),
        "path_type",
    ] = "SELL_THEN_RECOVERY"

    x.loc[
        (x["seg1_net"] > 0)
        & (x["seg2_net"] > 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "LATE_REVERSAL_SELL"

    # Successful bearish follow-through:
    # bearish candidate whose next 60-minute return is <= 0
    x["successful_sell_60m"] = (
        x["bearish_candidate"]
        & (x["forward_60m"] <= 0)
    )

    # Existing false SELL definition:
    # bearish candidate followed by positive 60-minute return
    x["false_sell_case"] = x["false_sell_60m"]

    groups = []

    for name, mask in [
        ("ALL", pd.Series(True, index=x.index)),
        ("SUCCESSFUL_SELL_60M", x["successful_sell_60m"]),
        ("FALSE_SELL_60M", x["false_sell_case"]),
    ]:
        g = x[mask].copy()

        if g.empty:
            continue

        groups.append({
            "group": name,
            "count": len(g),
            "avg_seg1_net": g["seg1_net"].mean(),
            "avg_seg2_net": g["seg2_net"].mean(),
            "avg_seg3_net": g["seg3_net"].mean(),
            "avg_late_sell_acceleration":
                g["late_sell_acceleration"].mean(),
            "avg_reversals": g["reversal_count"].mean(),
            "avg_travel": g["travel"].mean(),
            "avg_efficiency":
                g["directional_efficiency"].mean(),
            "high_first_rate":
                (g["high_low_sequence"] == "HIGH_FIRST").mean(),
            "low_first_rate":
                (g["high_low_sequence"] == "LOW_FIRST").mean(),
            "avg_forward_15m": g["forward_15m"].mean(),
            "avg_forward_30m": g["forward_30m"].mean(),
            "avg_forward_60m": g["forward_60m"].mean(),
            "avg_forward_120m": g["forward_120m"].mean(),
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
            "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
        })

    detail = pd.DataFrame(groups)

    path_summary = (
        x.groupby("path_type")
        .agg(
            count=("close", "size"),
            avg_body=("body", "mean"),
            avg_range=("range", "mean"),
            avg_travel=("travel", "mean"),
            avg_efficiency=("directional_efficiency", "mean"),
            avg_reversals=("reversal_count", "mean"),
            avg_forward_15m=("forward_15m", "mean"),
            avg_forward_30m=("forward_30m", "mean"),
            avg_forward_60m=("forward_60m", "mean"),
            avg_forward_120m=("forward_120m", "mean"),
            false_sell_rate=("false_sell_case", "mean"),
        )
        .reset_index()
    )

    return x, detail, path_summary


def main():
    api=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not api: raise RuntimeError("TWELVE_DATA_API_KEY is missing")
    print("V9.4 CANDLE DYNAMICS RESEARCH")
    m1=download(api); m1.to_csv("candle_dynamics_m1_v94.csv"); d=enrich(reconstruct(m1)); d.to_csv(OUT); t,p,f=summaries(d); t.to_csv("candle_dynamics_time_summary_v94.csv",index=False); p.to_csv("candle_dynamics_pattern_summary_v94.csv",index=False); f.to_csv("candle_dynamics_followthrough_summary_v94.csv",index=False); d[d.false_sell_60m].to_csv("candle_dynamics_false_sell_v94.csv")
    detailed, dynamics_summary, path_summary = detailed_intracandle_analysis(d)
    detailed.to_csv("candle_dynamics_detailed_v94.csv", index=False)
    dynamics_summary.to_csv("candle_dynamics_intracandle_summary_v94.csv", index=False)
    path_summary.to_csv("candle_dynamics_path_summary_v94.csv", index=False)
        print("\nDETAILED INTRACANDLE SUMMARY")
    print(dynamics_summary.to_string(index=False))

    print("\nINTRACANDLE PATH SUMMARY")
    print(path_summary.to_string(index=False))
    print(f"Complete M15 candles reconstructed: {len(d)}"); print("\nTIME SUMMARY"); print(t.to_string(index=False)); print("\nPATTERN SUMMARY"); print(p.to_string(index=False)); print("\nFOLLOW-THROUGH + MAE/MFE"); print(f.to_string(index=False))
if __name__=="__main__": main()
