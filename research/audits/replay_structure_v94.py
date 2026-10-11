"""Offline, research-only replay of historical V9.4 SELL structure decisions.

Usage:
  python research/audits/replay_structure_v94.py --candles historical_m15.csv \
    --journal trade_journal_v94.json --output research/audits/replay_results.json

CSV: datetime (UTC candle OPEN), open, high, low, close. No API keys, alerts,
orders, writes to production journals, or trading dependencies beyond pandas/numpy.
UNKNOWN means we cannot faithfully reconstruct the decision; never count as blocked.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from structure_risk_v94 import structure_atr_plan  # noqa: E402

MIN_HISTORY = 60
DEFAULT_COST_BPS = 10.0


def read_candles(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"datetime", "open", "high", "low", "close"}
    if not needed.issubset(df.columns):
        raise ValueError(f"Candle CSV missing columns: {sorted(needed - set(df.columns))}")
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="raise")
    if df["datetime"].duplicated().any():
        raise ValueError("Duplicate M15 candle timestamps")
    df = df.set_index("datetime").sort_index()
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="raise")
    if df[list(needed - {"datetime"})].isna().any().any():
        raise ValueError("Missing OHLC prices")
    if not all((df.index.minute % 15) == 0) or not all(df.index.second == 0):
        raise ValueError("Candle datetime must be aligned to UTC M15 OPEN times")
    return df


def replay(candles: pd.DataFrame, trades: list[dict]) -> dict:
    rows = []
    for trade in trades:
        if str(trade.get("side", "")).upper() != "SELL":
            continue
        result = {
            "model_time": trade.get("model_time"),
            "original_status": trade.get("status"),
            "replay_status": "UNKNOWN",
            "reason": "",
        }
        try:
            ts = pd.Timestamp(trade["model_time"])
            if ts.tzinfo is None:
                raise ValueError("Original model_time must contain UTC offset")
            ts = ts.tz_convert("UTC")
            entry = float(trade["entry"])
            # The model_time in V9.4 denotes the last completed candle's OPEN,
            # not the next candle's close. No future candles are included.
            history = candles.loc[candles.index <= ts].copy()
            if len(history) < MIN_HISTORY or ts not in history.index:
                raise ValueError("Insufficient or missing timestamp-aligned historical candles")
            # Original adaptive ATR multiple was not recorded in legacy trades.
            # Never guess it from future Biquote/calendar state.
            multiple = trade.get("atr_multiple")
            if multiple is None or not math.isfinite(float(multiple)):
                raise ValueError("Original adaptive ATR multiple not recorded")
            plan = structure_atr_plan(
                "SELL", history, atr_multiple=float(multiple),
                min_tp1_rr=2.0, swing_lookback=48,
                cost_bps=DEFAULT_COST_BPS, entry_price=entry,
            )
            result.update(
                replay_status="PASS" if plan["status"] == "ACTIVE" else "BLOCK",
                reason=str(plan["reason"]),
                structural_tp1=float(plan["tp1"]) if math.isfinite(plan["tp1"]) else None,
                structural_tp1_rr=float(plan["tp1_rr"]) if math.isfinite(plan["tp1_rr"]) else None,
            )
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            result["reason"] = str(exc)
        rows.append(result)
    outcomes = ("WIN", "LOSS", "OPEN", "AMBIGUOUS")
    summary = {
        decision: {outcome: sum(
            r["replay_status"] == decision and r["original_status"] == outcome
            for r in rows
        ) for outcome in outcomes}
        for decision in ("PASS", "BLOCK", "UNKNOWN")
    }
    return {"summary": summary, "records": rows,
            "disclaimer": "Paper outcomes only. UNKNOWN is not a prevented loss."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candles", type=Path, required=True)
    parser.add_argument("--journal", type=Path, default=ROOT / "trade_journal_v94.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in {args.journal.resolve(), args.candles.resolve()}:
        parser.error("Refusing to overwrite source inputs")
    data = replay(read_candles(args.candles), json.loads(args.journal.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data["summary"], indent=2))


if __name__ == "__main__":
    main()
