"""Research-only paired 120-minute SELL lifecycle audit; never places orders.

Requires historical M1 CSV and M15 production-parity CSV already on Oracle.
A: full position to SL / structural support TP / 120-minute close.
B: 33% at +0.5R, remainder follows A; SL is never moved.
Entries are next M1 open after a completed M15 signal. Stop-first OHLC ordering.
"""
import argparse
import json
from pathlib import Path
import sys
import pandas as pd


def run(args):
    sys.path.insert(0, str(Path(args.data_dir).resolve()))
    from structure_risk_v94 import structure_atr_plan

    root = Path(args.data_dir)
    m15 = pd.read_csv(root / "candle_dynamics_production_parity_detail_v94.csv",
                      parse_dates=["model_time"]).set_index("model_time").sort_index()
    m1 = pd.read_csv(root / "candle_dynamics_m1_v94.csv",
                     usecols=["datetime", "open", "high", "low", "close"],
                     parse_dates=["datetime"]).set_index("datetime").sort_index()
    signals = m15[m15.prod_plus_context2.astype(str).str.lower() == "true"]
    candidates = []
    skipped = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    for t in signals.index:
        et = t + pd.Timedelta(minutes=15)
        hist = m15.loc[:t, ["open", "high", "low", "close"]].tail(49)
        if et not in m1.index or len(hist) != 49 or not hist.index.equals(
            pd.date_range(end=t, periods=49, freq="15min")
        ):
            skip("missing_entry_or_m15_history")
            continue
        entry = float(m1.at[et, "open"])
        plan = structure_atr_plan(
            "SELL", hist.tail(48), entry_price=entry,
            atr_multiple=1.5, min_tp1_rr=2.0,
            swing_lookback=48, cost_bps=10
        )
        risk = float(plan["risk_distance"])
        if not pd.notna(risk) or risk <= 0:
            skip("invalid_risk")
            continue
        stop = float(plan["stop"])
        target = float(hist.low.iloc[:-1].min())
        if (entry - target) / risk < 2:
            skip("support_below_2R")
            continue
        future = m1.loc[et:et + pd.Timedelta(minutes=119)]
        if not future.index.equals(pd.date_range(et, periods=120, freq="min")):
            skip("incomplete_m1_window")
            continue

        # Determine the common full-position exit path before selecting
        # non-overlapping entries. Both arms retain this same exit time.
        end = future.index[-1]
        exit_price = float(future.iloc[-1]["close"])
        reason = "TIMEOUT"
        partial_time = None
        partial_price = entry - 0.5 * risk
        for minute, bar in future.iterrows():
            if bar.high >= stop:
                end, exit_price, reason = minute, stop, "SL"
                break
            if partial_time is None and bar.low <= partial_price:
                partial_time = minute
            if bar.low <= target:
                end, exit_price, reason = minute, target, "TP"
                break

        base_gross = (entry - exit_price) / risk
        partial_fraction = 0.33 if partial_time is not None else 0.0
        b_gross = partial_fraction * 0.5 + (1 - partial_fraction) * base_gross
        # Illustrative symmetric per-side execution cost on notional filled;
        # no financing, gaps, slippage, or real broker spread verification.
        rate = args.cost_bps / 10000
        a_cost = rate * (entry + exit_price) / risk
        b_cost = rate * (entry + partial_fraction * partial_price +
                         (1 - partial_fraction) * exit_price) / risk
        candidates.append({
            "entry_utc": et.isoformat(), "exit_utc": end.isoformat(),
            "entry": entry, "stop": stop, "target": target,
            "risk_points": risk, "exit_reason": reason,
            "partial_hit": partial_time is not None,
            "A_gross_R": base_gross, "B_gross_R": b_gross,
            "A_net_R": base_gross - a_cost, "B_net_R": b_gross - b_cost
        })

    selected = []
    last_exit = None
    for row in sorted(candidates, key=lambda x: x["entry_utc"]):
        if last_exit is None or row["entry_utc"] > last_exit:
            selected.append(row)
            last_exit = row["exit_utc"]

    def metrics(key):
        vals = [r[key] for r in selected]
        equity = peak = max_drawdown = 0.0
        for value in vals:
            equity += value
            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, peak - equity)
        return {
            "count": len(vals),
            "sum_R": round(sum(vals), 5),
            "mean_R": round(sum(vals) / len(vals), 5) if vals else None,
            "max_drawdown_R": round(max_drawdown, 5),
            "positive": sum(v > 0 for v in vals),
            "negative": sum(v < 0 for v in vals)
        }

    result = {
        "study": "V9.5 research-only paired +0.5R partial-exit diagnostic",
        "qualified_signals": len(signals),
        "qualifying_observations": len(candidates),
        "nonoverlapping_trades": len(selected),
        "partial_hits": sum(r["partial_hit"] for r in selected),
        "exit_reasons": {k: sum(r["exit_reason"] == k for r in selected)
                         for k in ("SL", "TP", "TIMEOUT")},
        "assumed_execution_cost_bps_per_side": args.cost_bps,
        "A_gross": metrics("A_gross_R"), "B_gross": metrics("B_gross_R"),
        "A_net": metrics("A_net_R"), "B_net": metrics("B_net_R"),
        "skipped": skipped,
        "limitations": [
            "Same-data exploratory study; not out-of-sample",
            "OHLC intraminute order unknown: stop wins ties",
            "Entry at next M1 open; timeout exit at final M1 close",
            "Fixed 1.5 ATR and 10bps structural cost-floor assumptions",
            "Illustrative symmetric execution costs; not broker-verified",
            "No gap/slippage/financing; historical flags omit live Biquote state",
            "One position at a time; gross and net R not compounded equity returns",
            "Does not modify V9.4 LIVE or V9.5 PAPER"
        ],
        "trades": selected
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="/home/ubuntu/v95-detector-dev")
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--output", default="/tmp/v95_half_r_paired_audit.json")
    args = parser.parse_args()
    if args.cost_bps < 0:
        parser.error("--cost-bps must be nonnegative")
    report = run(args)
    out = Path(args.output)
    if out.exists():
        parser.error("Output already exists; choose a new --output path")
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "trades"}, indent=2))
    print("Report:", str(out))


if __name__ == "__main__":
    main()
