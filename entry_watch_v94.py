"""Gold V9.4 automatic valid-entry watcher.

Recalculates the current V9.4 directional hierarchy from fresh market data,
then watches the corresponding structure-based >=2R valid-entry threshold.
Research alert only: reaching a threshold never submits or authorizes an order.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np

from candle_power_v94 import analyze_last_10_candles
from early_sell_v94 import detect_early_sell
from four_module_v94 import evaluate_four_modules
from free_gold_perpetuals_v90 import collect_free_perpetual_consensus
from gold_model import _download_symbol, expected_market_open
from gold_model_v90 import (
    five_minute_reversal_states,
    mother_candle_breakout,
    short_term_technical_trend,
)
from structure_risk_v94 import structure_atr_plan, valid_entry_for_min_rr
from telegram_alerts_v93 import send_telegram_alert


STATE_FILE = Path(os.getenv("V94_ENTRY_WATCH_STATE", "entry_watch_v94.json"))

M15_BARS = 1200
M5_BARS = 200
COST_BPS = 10
STOP_ATR_MULTIPLE = 1.5
MIN_RR = 2.0
SWING_LOOKBACK = 48


def _secret(name: str) -> str:
    value = str(os.getenv(name, "") or "").strip()
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def threshold_reached(side: str, price: float, threshold: float) -> bool:
    side = side.upper()
    if side == "BUY":
        return price <= threshold
    if side == "SELL":
        return price >= threshold
    return False


def _fresh_gold(api_key: str):
    gold = _download_symbol(
        api_key, "XAU/USD", M15_BARS, interval="15min"
    )
    if len(gold) < 60:
        raise RuntimeError(
            f"Only {len(gold)} M15 candles were returned; at least 60 are required."
        )
    if not expected_market_open(gold.index[-1]):
        raise RuntimeError(
            f"Latest XAU/USD candle {gold.index[-1]} is outside the accepted market session."
        )
    return gold


def _reversal_snapshot(api_key: str) -> dict:
    """Return the same current 5m reversal state used by the dashboard audit.

    Failure is neutral so a temporary 5m API problem cannot invent a reversal.
    """
    try:
        gold_5m = _download_symbol(
            api_key, "XAU/USD", M5_BARS, interval="5min"
        )
        if len(gold_5m) < 120:
            return {"current_signal": 0, "status": "UNAVAILABLE"}
        states = five_minute_reversal_states(gold_5m)
        return {
            "current_signal": int(states.signal.iloc[-1]),
            "status": "RAW CURRENT STATE",
        }
    except Exception:
        return {"current_signal": 0, "status": "UNAVAILABLE"}


def calculate_current_setup(api_key: str) -> dict:
    """Rebuild the V9.4 directional hierarchy and its valid-entry threshold."""
    gold = _fresh_gold(api_key)

    # GitHub has no live Streamlit-uploaded footprint. The V9.4 candle engine
    # explicitly supports footprint=None; candle pressure remains the primary input.
    power = analyze_last_10_candles(gold, footprint=None)
    early_sell = detect_early_sell(gold)
    perpetual = collect_free_perpetual_consensus()

    reversal = {"current_signal": 0, "status": "NOT NEEDED"}
    mother = mother_candle_breakout(gold)
    trend = short_term_technical_trend(gold)

    # Preserve the dashboard hierarchy exactly. Only calculate the 5m fallback
    # input when the first three directional layers did not decide the side.
    if power.signal in {"BUY", "SELL"}:
        side = power.signal
        basis = "10-candle power threshold"
    elif early_sell.signal == "SELL":
        side = "SELL"
        basis = f"early SELL acceleration ({early_sell.score:.2f})"
    
    else:
        reversal = _reversal_snapshot(api_key)
        four_module = evaluate_four_modules(
            power,
            mother_breakout=mother,
            short_trend=trend,
            reversal=reversal,
        )

        print("V9.4 FOUR-MODULE DIAGNOSTICS")
        for module in four_module.modules:
            print(f"{module.name}: {module.signal} ({module.score * 100:+.0f}%)")
        print(f"Four-module score: {four_module.score * 100:+.0f}%")
        print(f"Four-module qualified signal: {four_module.signal}")

        if four_module.score >= 0.05:
            side = "BUY"
            basis = "four-module directional lean"
        elif four_module.score <= -0.05:
            side = "SELL"
            basis = "four-module directional lean"
        else:
            side = "WAIT"
            basis = "mixed / insufficient directional evidence"

    result = {
        "side": side,
        "basis": basis,
        "model_time": gold.index[-1].isoformat(),
        "entry_reference": float(gold.close.iloc[-1]),
        "buy_power": float(power.buy_power),
        "sell_power": float(power.sell_power),
        "threshold": None,
        "structure_reason": "no directional setup",
    }

    if side not in {"BUY", "SELL"}:
        return result

    # Early SELL remains a warning layer only. It must not unlock an actionable
    # valid-entry threshold by itself.
    if basis.startswith("early SELL acceleration"):
        result["structure_reason"] = "early SELL warning cannot unlock risk sizing"
        return result

    plan = structure_atr_plan(
        side,
        gold,
        atr_multiple=STOP_ATR_MULTIPLE,
        min_tp1_rr=MIN_RR,
        swing_lookback=SWING_LOOKBACK,
        cost_bps=COST_BPS,
    )
    threshold = valid_entry_for_min_rr(plan, side, min_rr=MIN_RR)
    result["structure_reason"] = str(plan.get("reason", ""))
    result["stop_loss"] = float(plan.get("stop", np.nan))
    result["take_profit"] = float(plan.get("tp1", np.nan))
    result["reward_risk"] = float(plan.get("tp1_rr", np.nan))
    if np.isfinite(threshold) and float(threshold) > 0:
        result["threshold"] = float(threshold)
    return result


def check_once() -> str:
    api_key = _secret("TWELVE_DATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing.")

    previous = load_state()
    setup = calculate_current_setup(api_key)

    side = str(setup["side"]).upper()
    threshold = setup.get("threshold")
    threshold_ok = (
        side in {"BUY", "SELL"}
        and threshold is not None
        and math.isfinite(float(threshold))
        and float(threshold) > 0
    )

    # Always replace the saved setup with the newly calculated one.
    state = {
        "side": side,
        "basis": setup["basis"],
        "model_time": setup["model_time"],
        "entry_reference": round(float(setup["entry_reference"]), 4),
        "buy_power": round(float(setup["buy_power"]), 6),
        "sell_power": round(float(setup["sell_power"]), 6),
        "threshold": round(float(threshold), 4) if threshold_ok else None,
        "structure_reason": setup["structure_reason"],
    }

    if not threshold_ok:
        # No actionable threshold exists. Keep no stale BUY/SELL level.
        save_state(state)
        return (
            f"NO VALID THRESHOLD: {side}; basis={setup['basis']}; "
            f"reason={setup['structure_reason']}"
        )

    threshold = float(threshold)
    current_price = float(setup["entry_reference"])
    reached = threshold_reached(side, current_price, threshold)

    # Deduplicate by completed M15 model candle + side + rounded threshold.
    alert_key = f"{setup['model_time']}|{side}|{threshold:.2f}"
    if previous.get("last_alert_key"):
        state["last_alert_key"] = previous["last_alert_key"]
    if previous.get("last_alert_price") is not None:
        state["last_alert_price"] = previous["last_alert_price"]
    if reached and previous.get("last_alert_key") != alert_key:
        stop_loss = float(setup.get("stop_loss", np.nan))
        take_profit = float(setup.get("take_profit", np.nan))
        reward_risk = float(setup.get("reward_risk", np.nan))

        active = (
            np.isfinite(stop_loss)
            and np.isfinite(take_profit)
            and np.isfinite(reward_risk)
            and reward_risk >= MIN_RR
        )

        if active:
            message = (
                "Gold Version 9.4 — ACTIVE ENTRY\n"
                f"DIRECTION: {side}\n"
                f"Entry: USD {current_price:,.2f}\n"
                f"Stop loss: USD {stop_loss:,.2f}\n"
                f"Take profit: USD {take_profit:,.2f}\n"
                f"Reward/risk: {reward_risk:.2f}R\n"
                f"Basis: {setup['basis']}\n"
                "Mandatory SL + TP >=2R confirmed.\n"
                "Research alert only. No order was submitted."
            )
        else:
            message = (
                "Gold Version 9.4 — ENTRY BLOCKED\n"
                f"DIRECTION: {side}\n"
                f"Price: USD {current_price:,.2f}\n"
                "Threshold was reached, but fresh SL/TP >=2R validation failed.\n"
                "No active entry. No order was submitted."
            )

        delivery = send_telegram_alert(
            _secret("TELEGRAM_BOT_TOKEN"),
            _secret("TELEGRAM_CHAT_ID"),
            message,
        )
        if delivery.status == "SENT":
            state["last_alert_key"] = alert_key
            state["last_alert_price"] = round(current_price, 4)
    
        save_state(state)
        return f"{delivery.status}: {delivery.detail}"

    save_state(state)
    return (
        f"WATCHING {side}: XAU/USD {current_price:,.2f}; "
        f"threshold {threshold:,.2f}; reached={reached}; basis={setup['basis']}"
    )


if __name__ == "__main__":
    print(check_once())
