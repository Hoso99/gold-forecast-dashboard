"""Read-only historical 62 SELL journal / C2 Raw scenario diagnostic.

This is a 30-completed-M1-bar observational study, NOT a complete trade
backtest, realized fill simulation, or modification to V9.4/V9.5.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config

ROOT = Path("/home/ubuntu/v95-detector-dev")
SOURCES = [
    ROOT / "candle_dynamics_m1_v94.csv",
    ROOT / "research/data/v94_forward_m1.csv",
]
JOURNAL = ROOT / "trade_journal_v94.json"
EXIT = {"ADAPTIVE_EXIT", "EARLY_PROFIT_EXIT"}
WARN = {"REVERSAL_WARNING", "CONFIRMED_REVERSAL_CANDIDATE"}

def minute(value):
    return int(datetime.fromisoformat(str(value).replace("Z", "+00:00"))
               .astimezone(timezone.utc).timestamp() // 60)

def load():
    bars = {}
    conflicts = 0
    for path in SOURCES:
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                t = minute(row["datetime"])
                b = {k: float(row[v]) for k, v in
                     (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))}
                if t in bars and bars[t] != b:
                    conflicts += 1
                else:
                    bars[t] = b
    if conflicts:
        raise ValueError(f"Conflicting duplicate M1 candles: {conflicts}")
    return bars

def replay(record, index, bars, horizon, warmup):
    result = {
        "journal_index": index, "model_time": record.get("model_time"),
        "journal_status": record.get("status"), "entry": record.get("entry"),
        "stop_loss": record.get("stop_loss"), "take_profit": record.get("take_profit"),
    }
    try:
        t = minute(record["model_time"])
        entry = float(record["entry"])
        stop = float(record["stop_loss"])
        target = float(record["take_profit"])
        if not target < entry < stop:
            raise ValueError("invalid SELL entry/SL/TP geometry")
    except (KeyError, ValueError, TypeError) as exc:
        return dict(result, evaluation="INVALID_JOURNAL", detail=str(exc))
    # A signal timestamp is treated as an entry boundary, not a verified fill.
    # Feed only prior completed bars for warm-up, then post-entry bars.
    pre = [bars.get(t-k) for k in range(warmup, 0, -1)]
    post = [bars.get(t+k) for k in range(1, horizon+1)]
    if any(b is None for b in pre):
        return dict(result, evaluation="MISSING_WARMUP",
                    missing_warmup=sum(b is None for b in pre))
    if any(b is None for b in post):
        return dict(result, evaluation="MISSING_FORWARD",
                    missing_forward=sum(b is None for b in post))
    model = HybridC(cfg=Config(power_mode="raw", scenario_monitor_enabled=True))
    for b in pre:
        model.on_completed_m1(b)
    model.open_initial(entry, stop, target)
    counts = Counter()
    actions = Counter()
    first_warning = None
    first_confirmed = None
    first_raw_exit = None
    first_protection = None
    first_any_warning = None
    for offset, b in enumerate(post, 1):
        # Preserve baseline state-machine behavior. Protective level touches
        # are reported, not executed, because journal fills are not known.
        outcome = model.on_completed_m1(b)
        action = outcome["action"]
        scenario = outcome.get("scenario_monitor", {}).get("state", "UNAVAILABLE")
        actions[action] += 1
        counts[scenario] += 1
        if scenario in WARN and first_any_warning is None:
            first_any_warning = offset
        if scenario == "REVERSAL_WARNING" and first_warning is None:
            first_warning = offset
        if scenario == "CONFIRMED_REVERSAL_CANDIDATE" and first_confirmed is None:
            first_confirmed = offset
        if action in EXIT and first_raw_exit is None:
            first_raw_exit = offset
        if action in ("PROTECTIVE_SL", "PROTECTIVE_TP", "INCONCLUSIVE_SL_TP_ORDER") and first_protection is None:
            first_protection = {"minute": offset, "action": action}
            # Once protective level is touched, subsequent labels no longer
            # represent an open position; stop observational position replay.
            break
    # Separate simple 30m OHLC reference path, not an execution simulation.
    touch = None
    for offset, b in enumerate(post, 1):
        sl = b["h"] >= stop
        tp = b["l"] <= target
        if sl or tp:
            touch = {"minute": offset, "type":
                     "BOTH_ORDER_UNKNOWN" if sl and tp else "SL" if sl else "TP"}
            break
    risk = stop-entry
    result.update({
        "evaluation": "EVALUATED_30M", "first_scenario_warning_minute": first_warning,
        "first_confirmed_candidate_minute": first_confirmed,
        "first_any_reversal_label_minute": first_any_warning,
        "first_c2_raw_exit_request_minute": first_raw_exit,
        "first_protective_event": first_protection,
        "first_30m_sl_tp_touch": touch,
        "30m_close_change_usd_per_oz": round(post[-1]["c"]-entry, 5),
        "30m_close_reference_r": round((entry-post[-1]["c"])/risk, 5),
        "scenario_counts_until_protection": dict(counts),
        "c2_raw_action_counts_until_protection": dict(actions),
    })
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--horizon", type=int, default=30)
    p.add_argument("--warmup", type=int, default=100)
    args = p.parse_args()
    if args.horizon < 1 or args.warmup < 16:
        p.error("horizon must be positive and warmup >=16")
    dest = Path(args.output)
    if dest.exists():
        p.error("Output exists; choose a fresh path")
    bars = load()
    records = json.loads(JOURNAL.read_text())
    sells = [(i, r) for i, r in enumerate(records, 1)
             if str(r.get("side", "")).upper() == "SELL"]
    rows = [replay(r, i, bars, args.horizon, args.warmup) for i, r in sells]
    evaluated = [r for r in rows if r["evaluation"] == "EVALUATED_30M"]
    status = {}
    for name in sorted({str(r.get("journal_status")) for r in rows}):
        group = [r for r in evaluated if str(r.get("journal_status")) == name]
        status[name] = {
            "total_journal": sum(str(r.get("journal_status")) == name for r in rows),
            "evaluated": len(group),
            "any_reversal_label": sum(r["first_any_reversal_label_minute"] is not None for r in group),
            "confirmed_candidate": sum(r["first_confirmed_candidate_minute"] is not None for r in group),
            "raw_exit_request": sum(r["first_c2_raw_exit_request_minute"] is not None for r in group),
            "sl_touch_30m": sum(r["first_30m_sl_tp_touch"] is not None and
                                 r["first_30m_sl_tp_touch"]["type"] == "SL" for r in group),
            "tp_touch_30m": sum(r["first_30m_sl_tp_touch"] is not None and
                                 r["first_30m_sl_tp_touch"]["type"] == "TP" for r in group),
            "ambiguous_touch_30m": sum(r["first_30m_sl_tp_touch"] is not None and
                                 r["first_30m_sl_tp_touch"]["type"] == "BOTH_ORDER_UNKNOWN" for r in group),
        }
    report = {
        "study": "V9.4 SELL journal C2 Raw scenario 30m observational replay",
        "signals_total": len(sells), "candles_loaded": len(bars),
        "evaluation_counts": dict(Counter(r["evaluation"] for r in rows)),
        "journal_status_counts": dict(Counter(str(r.get("journal_status")) for r in rows)),
        "by_status": status,
        "limitations": [
            "30m observation, not full lifetime replay of each journal trade",
            "Journal entry timestamp treated as boundary; actual fill timing unverified",
            "Only prior completed M1 bars used to warm up; no look-ahead",
            "C2 Raw exit requests are not fills; no spread/slippage or next-bar execution",
            "No change to live V9.4, V9.5 PAPER or C2 Raw decision logic",
            "Scenario labels are observational, not validated accuracy or counterfactual savings",
            "Overlapping journal signals are not independent statistical samples",
            "Protective SL/TP same-bar order is unknown",
            "Historical journal WIN/LOSS labels may refer to later outcomes than 30m",
        ],
        "signals": rows,
    }
    with dest.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(json.dumps({k: v for k, v in report.items() if k != "signals"}, indent=2))
    for r in rows:
        if r["evaluation"] != "EVALUATED_30M":
            print("NOT_EVALUATED", r["journal_index"], r["evaluation"])

if __name__ == "__main__":
    main()
