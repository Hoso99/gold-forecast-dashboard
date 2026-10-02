"""V9.4 candle-window research comparison.

Compares 8, 10, 12, 15 and 20 completed M15 candles.
Research only. Does not modify the live V9.4 model or live trade journal.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from candle_power_v94 import analyze_last_10_candles
from gold_model import _download_symbol
from structure_risk_v94 import structure_atr_plan


WINDOWS = [8, 10, 12, 15, 20]

M15_BARS = 5000
SWING_LOOKBACK = 48
STOP_ATR_MULTIPLE = 1.5
MIN_RR = 2.0
COST_BPS = 10

OUTPUT_FILE = Path("candle_window_comparison_v94.csv")
SUMMARY_FILE = Path("candle_window_summary_v94.csv")


def proportional_sell_breadth(bars: int) -> int:
    """V9.4 uses 6/10 SELL candles = 60% breadth."""
    return math.ceil(bars * 0.60)


print("V9.4 CANDLE-WINDOW RESEARCH")
print("Windows:", WINDOWS)

for bars in WINDOWS:
    print(
        f"{bars} candles = {bars * 15 / 60:.2f} hours; "
        f"SELL breadth required = "
        f"{proportional_sell_breadth(bars)}/{bars}"
    )

def diagnose_window_sell_quality(power, bars: int) -> dict:
    """Apply V9.4 SELL-quality checks fairly across different windows."""

    rows = power.rows

    if rows is None or rows.empty:
        return {
            "status": "UNAVAILABLE",
            "score": 0.0,
            "checks_passed": 0,
            "checks_total": 0,
            "reasons": ["No diagnostic rows available."],
        }

    recent5 = rows.tail(5)
    recent3 = rows.tail(3)
    recent2 = rows.tail(2)

    sell_count = int(
        (rows["Direction"] == "SELL").sum()
    )
    sell_count_5 = int(
        (recent5["Direction"] == "SELL").sum()
    )
    sell_count_2 = int(
        (recent2["Direction"] == "SELL").sum()
    )

    recent_body = float(
        recent3["Body pressure"].mean()
    )
    recent_close = float(
        recent3["Close-location pressure"].mean()
    )
    recent_wick = float(
        recent3["Wick pressure"].mean()
    )
    recent_impulse = float(
        recent3["ATR impulse"].mean()
    )
    recent_power = float(
        recent3["Power score"].mean()
    )

    checks = {
        "sell_breadth":
            sell_count >= proportional_sell_breadth(bars),

        "recent_persistence":
            sell_count_5 >= 3,

        "latest_persistence":
            sell_count_2 == 2,

        "bearish_body":
            recent_body < 0,

        "bearish_close":
            recent_close < 0,

        "bearish_impulse":
            recent_impulse < 0,

        "bearish_recent_power":
            recent_power < 0,

        "no_strong_lower_wick_rejection":
            recent_wick <= 0.20,

        "sell_acceleration":
            power.pressure_acceleration <= 0,
    }

    passed = sum(
        bool(value)
        for value in checks.values()
    )
    total = len(checks)

    if passed >= 8:
        status = "CONFIRMED"
    elif passed >= 5:
        status = "MIXED"
    else:
        status = "REJECTED"

    reasons = [
        name
        for name, value in checks.items()
        if not value
    ]

    return {
        "status": status,
        "score": passed / total,
        "checks_passed": passed,
        "checks_total": total,
        "sell_count": sell_count,
        "sell_count_5": sell_count_5,
        "sell_count_2": sell_count_2,
        "recent_body": recent_body,
        "recent_close": recent_close,
        "recent_wick": recent_wick,
        "recent_impulse": recent_impulse,
        "recent_power": recent_power,
        "pressure_acceleration":
            float(power.pressure_acceleration),
        "checks": checks,
        "reasons": reasons,
    }

def evaluate_sell_outcome(
    future: pd.DataFrame,
    stop_loss: float,
    take_profit: float,
) -> dict:
    """Find whether SL or TP is reached first after a historical SELL."""

    for candle_time, candle in future.iterrows():

        hit_sl = float(candle["high"]) >= stop_loss
        hit_tp = float(candle["low"]) <= take_profit

        if hit_sl and hit_tp:
            return {
                "outcome": "AMBIGUOUS",
                "outcome_r": np.nan,
                "exit_time": candle_time,
            }

        if hit_sl:
            return {
                "outcome": "LOSS",
                "outcome_r": -1.0,
                "exit_time": candle_time,
            }

        if hit_tp:
            return {
                "outcome": "WIN",
                "outcome_r": MIN_RR,
                "exit_time": candle_time,
            }

    return {
        "outcome": "OPEN",
        "outcome_r": np.nan,
        "exit_time": pd.NaT,
    }

def run_historical_comparison(gold: pd.DataFrame) -> pd.DataFrame:
    """Replay each historical M15 point for all five candle windows."""

    records = []

    next_available_index = {
        bars: 0
        for bars in WINDOWS
    }

    warmup = max(
        SWING_LOOKBACK + 20,
        max(WINDOWS) + 20,
    )

    for i in range(warmup, len(gold)):

        history = gold.iloc[: i + 1].copy()
        model_time = history.index[-1]
        entry = float(history["close"].iloc[-1])

        future = gold.iloc[i + 1:].copy()

        for bars in WINDOWS:

            power = analyze_last_10_candles(
                history,
                footprint=None,
                bars=bars,
            )

            quality = diagnose_window_sell_quality(
                power,
                bars,
            )

            raw_signal = str(power.signal).upper()

            actionable_sell = (
                raw_signal == "SELL"
                and quality["status"] == "CONFIRMED"
            )

            decision = (
                "SELL"
                if actionable_sell
                else "WAIT"
            )

            record = {
                "model_time": model_time,
                "window": bars,
                "hours": bars * 15 / 60,
                "decision": decision,
                "raw_signal": raw_signal,
                "buy_power": float(power.buy_power),
                "sell_power": float(power.sell_power),
                "pressure_acceleration":
                    float(power.pressure_acceleration),
                "quality_status": quality["status"],
                "quality_score": quality["score"],
                "checks_passed":
                    quality["checks_passed"],
                "checks_total":
                    quality["checks_total"],
                "sell_count":
                    quality.get("sell_count", 0),
                "sell_count_5":
                    quality.get("sell_count_5", 0),
                "sell_count_2":
                    quality.get("sell_count_2", 0),
                "failed_checks":
                    "|".join(quality.get("reasons", [])),
                "entry": entry,
                "stop_loss": np.nan,
                "take_profit": np.nan,
                "stop_distance": np.nan,
                "atr14": np.nan,
                "swing_high": np.nan,
                "outcome": "",
                "outcome_r": np.nan,
                "exit_time": pd.NaT,
                "bars_to_outcome": np.nan,
            }

            trade_available = (
                i >= next_available_index[bars]
            )

            independent_sell = (
                actionable_sell
                and trade_available
            )

            record["independent_entry"] = independent_sell

            if independent_sell:

                plan = structure_atr_plan(
                    "SELL",
                    history,
                    atr_multiple=STOP_ATR_MULTIPLE,
                    min_tp1_rr=MIN_RR,
                    swing_lookback=SWING_LOOKBACK,
                    cost_bps=COST_BPS,
                    entry_price=entry,
                )

                stop_loss = float(
                    plan.get("stop", np.nan)
                )

                atr14 = float(
                    plan.get("atr", np.nan)
                )

                swing_high = float(
                    plan.get("swing", np.nan)
                )

                if np.isfinite(stop_loss):

                    stop_distance = abs(
                        entry - stop_loss
                    )

                    if stop_distance > 0:

                        take_profit = (
                            entry
                            - MIN_RR * stop_distance
                        )

                        result = evaluate_sell_outcome(
                            future,
                            stop_loss,
                            take_profit,
                        )

                        record["stop_loss"] = stop_loss
                        record["take_profit"] = take_profit
                        record["stop_distance"] = stop_distance
                        record["atr14"] = atr14
                        record["swing_high"] = swing_high
                        record["outcome"] = result["outcome"]
                        record["outcome_r"] = result["outcome_r"]
                        record["exit_time"] = result["exit_time"]

                        if pd.notna(result["exit_time"]):
                            exit_pos = gold.index.get_loc(
                                result["exit_time"]
                            )
                            record["bars_to_outcome"] = (
                                exit_pos - i
                            )
                            next_available_index[bars] = (
                                exit_pos + 1
                            )
                        else:
                            next_available_index[bars] = len(gold)

                    else:
                        record["decision"] = "WAIT"
                        record["independent_entry"] = False
                        record["outcome"] = "INVALID STOP DISTANCE"

                else:
                    record["decision"] = "WAIT"
                    record["independent_entry"] = False
                    record["outcome"] = "NO VALID STRUCTURE STOP"

            records.append(record)

    return pd.DataFrame(records)


def build_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Summarize performance and selectivity for each candle window."""

    summaries = []

    for bars in WINDOWS:

        group = results[
            results["window"] == bars
        ].copy()

        sells = group[
            group["decision"] == "SELL"
        ].copy()

        independent_sells = sells[
            sells["independent_entry"] == True
        ].copy()

        resolved = independent_sells[
            independent_sells["outcome"].isin(
                ["WIN", "LOSS"]
            )
        ].copy()

        wins = int(
            (resolved["outcome"] == "WIN").sum()
        )
        losses = int(
            (resolved["outcome"] == "LOSS").sum()
        )

        ambiguous = int(
            (
                independent_sells["outcome"]
                == "AMBIGUOUS"
            ).sum()
        )

        open_trades = int(
            (
                independent_sells["outcome"]
                == "OPEN"
            ).sum()
        )

        total_decisions = len(group)
        sell_signals = len(sells)
        independent_trades = len(independent_sells)
        wait_signals = int(
            (group["decision"] == "WAIT").sum()
        )

        win_rate = (
            wins / len(resolved)
            if len(resolved)
            else np.nan
        )

        total_r = float(
            resolved["outcome_r"].sum()
        ) if len(resolved) else 0.0

        expectancy_r = (
            float(resolved["outcome_r"].mean())
            if len(resolved)
            else np.nan
        )

        avg_bars_to_outcome = (
            float(
                resolved["bars_to_outcome"].mean()
            )
            if len(resolved)
            else np.nan
        )

        equity_curve = (
            resolved["outcome_r"]
            .fillna(0.0)
            .cumsum()
        )

        if len(equity_curve):
            running_peak = equity_curve.cummax()
            drawdown = equity_curve - running_peak
            max_drawdown_r = float(
                drawdown.min()
            )
        else:
            max_drawdown_r = 0.0

        max_consecutive_losses = 0
        current_losses = 0

        for outcome in resolved["outcome"]:
            if outcome == "LOSS":
                current_losses += 1
                max_consecutive_losses = max(
                    max_consecutive_losses,
                    current_losses,
                )
            else:
                current_losses = 0

        summaries.append({
            "window": bars,
            "hours": bars * 15 / 60,
            "total_decisions": total_decisions,
            "sell_signals": sell_signals,
            "independent_trades": independent_trades,
            "wait_signals": wait_signals,
            "resolved_trades": len(resolved),
            "wins": wins,
            "losses": losses,
            "ambiguous": ambiguous,
            "open": open_trades,
            "win_rate": win_rate,
            "total_r": total_r,
            "expectancy_r": expectancy_r,
            "max_drawdown_r": max_drawdown_r,
            "max_consecutive_losses":
                max_consecutive_losses,
            "avg_bars_to_outcome":
                avg_bars_to_outcome,
        })

    return pd.DataFrame(summaries)

def main():
    api_key = str(
        __import__("os").environ.get(
            "TWELVE_DATA_API_KEY",
            "",
        )
    ).strip()

    if not api_key:
        raise RuntimeError(
            "TWELVE_DATA_API_KEY is missing."
        )

    print("\nDownloading historical XAU/USD M15 data...")

    gold = _download_symbol(
        api_key,
        "XAU/USD",
        M15_BARS,
        interval="15min",
    )

    gold = gold.sort_index().copy()

    print(
        f"Historical candles loaded: {len(gold)}"
    )
    print(
        f"From: {gold.index[0]}"
    )
    print(
        f"To:   {gold.index[-1]}"
    )

    print(
        "\nRunning 8/10/12/15/20 "
        "candle comparison..."
    )

    results = run_historical_comparison(gold)

    summary = build_summary(results)

    results.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    print("\nCOMPARISON COMPLETE")
    print(
        f"Detailed journal: {OUTPUT_FILE}"
    )
    print(
        f"Summary: {SUMMARY_FILE}"
    )

    print("\nWINDOW SUMMARY")
    print(
        summary.to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
