"""Offline V9.5 31-variant exit comparison on *proxy* SELL entries.

This is a plumbing/sensitivity study, NOT a V9.4 signal replay or validated
V9.5 entry model. No orders, alerts, network, or broker interactions.
M1 timestamps assumed OPEN-stamped, UNVERIFIED. Results are illustrative.
"""
from __future__ import annotations
import csv
import json
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from v95_exit_variant_engine import simulate_sell, variants

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "research/data/v94_forward_m1.csv"


def load():
    rows = []
    with DATA.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append({"t": datetime.fromisoformat(r["datetime"]),
                         **{k: float(r[k]) for k in ("open", "high", "low", "close")}})
    rows.sort(key=lambda x: x["t"])
    if len({r["t"] for r in rows}) != len(rows):
        raise ValueError("Duplicate timestamps; abort")
    return rows


def contiguous(rows):
    return all(b["t"] - a["t"] == timedelta(minutes=1)
               for a, b in zip(rows, rows[1:]))


def run():
    bars = load()
    choices = variants()
    if len(choices) != 31:
        raise ValueError("Unexpected variant count")
    trades = []
    # Fixed, predeclared proxy rule: preceding 30 M1 bars have lower close,
    # bearish last 15-minute segment, then SELL at NEXT bar open.
    # No future bars are used to select a signal or initial stop.
    # Non-overlap: at most one entry every 360 minutes.
    i = 45
    while i + 360 < len(bars):
        history = bars[i-30:i]
        path = bars[i:i+360]
        if not contiguous(bars[i-30:i+360]):
            i += 15
            continue
        if not (history[-1]["close"] < history[0]["close"] and
                history[-1]["close"] < history[-15]["close"]):
            i += 15
            continue
        entry = path[0]["open"]
        # Historical swing high plus 0.15 * historical average M1 range;
        # proxy risk, not V9.4's structural M15 + ATR14 stop.
        avg_range = statistics.mean(b["high"]-b["low"] for b in history)
        stop = max(b["high"] for b in history) + 0.15 * avg_range
        if stop <= entry or not math.isfinite(stop):
            i += 15
            continue
        # Constant historical M1 range proxy, not completed M5 ATR14.
        atr_proxy = avg_range * math.sqrt(5)
        results = {}
        for v in choices:
            kwargs = {k: value for k, value in v.items() if k != "name"}
            results[v["name"]] = simulate_sell(
                path, entry, stop, atr_proxy, cost_points=0.30, **kwargs)
        trades.append({"time": path[0]["t"].isoformat(), "results": results})
        i += 360
    if len(trades) < 4:
        return {"status": "INSUFFICIENT_NONOVERLAPPING_PROXY_TRADES",
                "trades": len(trades), "variants": len(choices)}
    split = int(len(trades) * 0.7)
    def metrics(sample, name):
        vals = [t["results"][name]["net_r"] for t in sample]
        return {"n": len(vals), "mean_net_r": round(statistics.mean(vals), 5),
                "median_net_r": round(statistics.median(vals), 5),
                "positive_pct": round(100*sum(x>0 for x in vals)/len(vals), 2)}
    return {
        "status": "EXPLORATORY_PROXY_NOT_V95_VALIDATION",
        "source": str(DATA.relative_to(ROOT)),
        "proxy_entries": len(trades), "variant_count": len(choices),
        "development": {v["name"]: metrics(trades[:split], v["name"]) for v in choices},
        "holdout": {v["name"]: metrics(trades[split:], v["name"]) for v in choices},
        "limitations": [
            "Proxy entries are NOT actual V9.4/V9.5 SELL signals",
            "M1 OPEN timestamp assumption is unverified",
            "Initial stop is proxy swing/range, NOT M15 ATR14 structural stop",
            "M5 trailing ATR is proxied, not observed completed M5 ATR14",
            "Illustrative fixed 0.30 point roundtrip cost; no bid/ask or fills",
            "Sparse non-overlapping observations; not a performance claim",
            "Existing engine's candle handling must be independently audited",
            "No dynamic market-data EXIT SELL NOW model is implemented",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
