"""Research-only adaptive exit experiment. Independent fixed-entry shadow; no deployment.
Caveats: technical PAPER approximation, historical news and partials unavailable.
2026 is diagnostic-only and was already inspected. Original and strict entries are
computed independently; compare ONLY identical timestamps.
"""
import collections
import datetime as dt
import importlib.util
import json
import math
import sqlite3
from pathlib import Path
from urllib.parse import quote

SOURCE = Path("research/historical/v95_m1_paper_approx.py")
src = SOURCE.read_text()
structure = "if m15[-1]['c']>max(x['h'] for x in m15[-4:-1]):"
momentum = """elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=3
                              and m5[-1]['c']>m5[-2]['c'] and h1[-1]['c']>h1[-2]['c']):"""
assert src.count(structure) == src.count(momentum) == 1
strict = src.replace(structure, """if (m15[-1]['c']>max(x['h'] for x in m15[-4:-1])
                                +0.25*atr15(aggs[15]['bars'])
                                and m5[-1]['c']>m5[-2]['c']):""").replace(momentum, """elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=4
                              and m5[-1]['c']>m5[-2]['c']
                              and h1[-1]['c']>h1[-2]['c']
                              and c>active['entry']+0.25*atr15(aggs[15]['bars'])):""")
assert strict != src

runs = {}
module = None
for name, code in (("original", src), ("strict", strict)):
    spec = importlib.util.spec_from_loader("shadow_" + name, loader=None)
    m = importlib.util.module_from_spec(spec)
    exec(compile(code, str(SOURCE), "exec"), m.__dict__)
    detector = m.technical_signal
    def sweep75(m1, aggs, fn=detector):
        signal = fn(m1, aggs)
        return signal if signal and signal["detector"] == "SWEEP" and signal["power"] >= 75 else None
    m.technical_signal = sweep75
    m.replay()
    report = json.loads(Path("v95-m1-paper-approx-results.json").read_text())
    runs[name] = {t["entry_utc"]: t for t in report["trades"]}
    print("BASELINE", name, len(runs[name]), flush=True)
    module = m

assert runs["original"].keys() == runs["strict"].keys(), "Original and strict entries diverged"
UTC = dt.timezone.utc
ONE = dt.timedelta(minutes=1)
MAX_HOLD = 240
COST_BPS = 5
# Adaptive candidate frozen in advance: confirmed reversal AND adverse movement,
# with a protective timeout. No parameter search against 2026.
def adaptive(trade):
    entry_time = dt.datetime.fromisoformat(trade["entry_utc"])
    begin = entry_time - dt.timedelta(hours=8)
    end = entry_time + dt.timedelta(minutes=MAX_HOLD)
    bars = []
    for filename in module.NAMES:
        uri = "file:" + quote(str(module.ROOT / filename), safe="/") + "?mode=ro&immutable=1"
        with sqlite3.connect(uri, uri=True) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute(
                "SELECT minute_utc,open,high,low,close FROM candles WHERE minute_utc>=? AND minute_utc<=? ORDER BY minute_utc",
                (begin.date().isoformat(), (end.date()+dt.timedelta(days=1)).isoformat())
            )
            for stamp,o,h,l,c in rows:
                t = dt.datetime.fromisoformat(stamp).replace(tzinfo=UTC)
                if begin <= t <= end:
                    bars.append((t,o,h,l,c))
    bars.sort(key=lambda x:x[0])
    aggs = {n:{"part":None,"bars":collections.deque(maxlen=25)} for n in (5,15,60,240)}
    last = None
    entry = float(trade["entry"])
    stop = float(trade["stop"])
    target = float(trade["target"])
    risk = float(trade["risk"])
    for t,o,h,l,c in bars:
        if last is not None and t-last != ONE and t>entry_time:
            return {"outcome":"CENSORED_GAP","net_r":None,"exit_utc":last.isoformat()}
        module.aggregate_update(aggs,t,o,h,l,c)
        last = t
        if t<=entry_time: continue
        if h>=stop:
            outcome, fill = "SL", max(stop,o)
        elif l<=target:
            outcome, fill = "TP", target
        else:
            outcome, fill = None, None
            m5 = list(aggs[5]["bars"])
            m15 = list(aggs[15]["bars"])
            h1 = list(aggs[60]["bars"])
            ready = (module.consecutive(m5,5,6)
                     and module.consecutive(m15,15,18)
                     and module.consecutive(h1,60,3)
                     and m5[-1]["t"] >= module.bucket(t,5)-dt.timedelta(minutes=5)
                     and m15[-1]["t"] >= module.bucket(t,15)-dt.timedelta(minutes=15)
                     and h1[-1]["t"] >= module.bucket(t,60)-dt.timedelta(minutes=60))
            if ready:
                a = module.atr15(m15)
                if a is not None and math.isfinite(a) and a>0:
                    structure = (m15[-1]["c"] > max(x["h"] for x in m15[-4:-1]) + 0.25*a
                                 and m5[-1]["c"] > m5[-2]["c"])
                    momentum = (sum(m5[-i]["c"]>m5[-i-1]["c"] for i in range(1,5)) >= 4
                                and h1[-1]["c"] > h1[-2]["c"]
                                and c > entry + 0.25*a)
                    # Lock in gains only on confirmed bullish M5 shift and >= 1R open profit.
                    protect = ((entry-c)/risk >= 1.0
                               and m5[-1]["c"] > m5[-2]["c"]
                               and sum(m5[-i]["c"]>m5[-i-1]["c"] for i in range(1,5)) >= 3)
                    if structure or momentum or protect:
                        outcome, fill = ("ADAPTIVE_STRUCTURE" if structure else
                                         "ADAPTIVE_MOMENTUM" if momentum else
                                         "ADAPTIVE_PROFIT_PROTECT"), c
            if outcome is None and t-entry_time >= dt.timedelta(minutes=MAX_HOLD):
                outcome, fill = "TIMEOUT_240M", c
        if outcome is not None:
            net = (entry-fill)/risk - entry*(COST_BPS/10000)/risk
            return {"outcome":outcome,"net_r":round(net,7),"exit_utc":t.isoformat()}
    return {"outcome":"CENSORED_END","net_r":None,"exit_utc":None}

pairs = []
for index, (timestamp, orig) in enumerate(sorted(runs["original"].items()), 1):
    strict_trade = runs["strict"][timestamp]
    candidate = adaptive(orig)
    pairs.append({"entry_utc":timestamp,"year":orig["year"],
                  "original_outcome":orig["outcome"],"strict_outcome":strict_trade["outcome"],
                  "adaptive_outcome":candidate["outcome"],
                  "original_net_r":orig.get("net_r"),"strict_net_r":strict_trade.get("net_r"),
                  "adaptive_net_r":candidate["net_r"]})
    if index%25==0: print("ADAPTIVE_PROGRESS", index, flush=True)

def stats(rows, arm):
    completed = [r for r in rows if r[arm+"_net_r"] is not None]
    vals = [r[arm+"_net_r"] for r in completed]
    wins = sum(v>0 for v in vals)
    losses = -sum(v for v in vals if v<0)
    return {"entries":len(rows),"completed":len(vals),"censored":len(rows)-len(vals),
            "mean_net_r":round(sum(vals)/len(vals),6) if vals else None,
            "sum_net_r":round(sum(vals),6),
            "win_rate":round(wins/len(vals),6) if vals else None,
            "profit_factor":round(sum(v for v in vals if v>0)/losses,6) if losses else None}

def paired(rows, arm):
    eligible = [r for r in rows if r["original_net_r"] is not None and r[arm+"_net_r"] is not None]
    delta = [r[arm+"_net_r"]-r["original_net_r"] for r in eligible]
    return {"paired_completed":len(delta),"unresolved_pairs":len(rows)-len(delta),
            "sum_delta_r":round(sum(delta),6),
            "mean_delta_r":round(sum(delta)/len(delta),6) if delta else None}

report = {"research_only":True,"NOT_FULL_V95_PAPER_REPLAY":True,
          "news_gate":"NOT_TESTED","manual_partials":"NOT_TESTED",
          "execution":"M1 close reference, 5bps cost; stop first; independent fixed-entry shadow",
          "adaptive_max_hold_minutes":MAX_HOLD,
          "warning":"Adaptive fixed-entry simulation does not reproduce portfolio occupancy/daily lock; 2026 already inspected",
          "all_years":{a:stats(pairs,a) for a in ("original","strict","adaptive")},
          "training_2020_2025":{a:stats([r for r in pairs if r["year"]<2026],a) for a in ("original","strict","adaptive")},
          "diagnostic_2026":{a:stats([r for r in pairs if r["year"]==2026],a) for a in ("original","strict","adaptive")},
          "paired_training":{a:paired([r for r in pairs if r["year"]<2026],a) for a in ("strict","adaptive")},
          "yearly":{str(y):{a:stats([r for r in pairs if r["year"]==y],a) for a in ("original","strict","adaptive")} for y in range(2020,2027)},
          "pairs":pairs}
Path("v95-adaptive-exit-challenger.json").write_text(json.dumps(report,indent=2)+"\n")
print("ADAPTIVE_SUMMARY",json.dumps({k:v for k,v in report.items() if k not in ("pairs","yearly")}))
print("ADAPTIVE_RESEARCH_COMPLETE")
