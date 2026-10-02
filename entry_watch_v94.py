"""Gold V9.4 automatic valid-entry watcher.

Recalculates the current V9.4 directional hierarchy from fresh market data,
then watches the corresponding structure-based >=2R valid-entry threshold.
Research alert only: reaching a threshold never submits or authorizes an order.
"""
from __future__ import annotations

import json
import math
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from candle_power_v94 import analyze_last_10_candles, diagnose_sell_quality
from early_sell_v94 import detect_early_sell
from four_module_v94 import evaluate_four_modules
from free_gold_perpetuals_v90 import collect_free_perpetual_consensus
from gold_model import _download_symbol, expected_market_open, current_gold_price
from gold_model_v90 import (
    five_minute_reversal_states,
    mother_candle_breakout,
    short_term_technical_trend,
)
from structure_risk_v94 import structure_atr_plan, valid_entry_for_min_rr
from telegram_alerts_v93 import send_telegram_alert


STATE_FILE = Path(os.getenv("V94_ENTRY_WATCH_STATE", "entry_watch_v94.json"))
JOURNAL_FILE = Path(os.getenv("V94_TRADE_JOURNAL", "trade_journal_v94.json"))

M15_BARS = 1200
M5_BARS = 200
COST_BPS = 10
STOP_ATR_MULTIPLE = 1.5
BUILDING_ATR_MULTIPLE = 1.75
HIGH_ATR_MULTIPLE = 2.00
EXTREME_ATR_MULTIPLE = 2.25
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
def load_journal() -> list:
        if not JOURNAL_FILE.exists():
            return []
        try:
            data = json.loads(JOURNAL_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (OSError, json.JSONDecodeError):
            return []


def save_journal(journal: list) -> None:
    JOURNAL_FILE.write_text(
        json.dumps(journal, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_open_trades(gold) -> None:
    journal = load_journal()
    changed = False

    for trade in journal:
        if trade.get("status") != "OPEN":
            continue

        side = str(trade.get("side", "")).upper()
        if side != "SELL":
            continue

        entry_time = pd.Timestamp(trade["model_time"])
        stop_loss = float(trade["stop_loss"])
        take_profit = float(trade["take_profit"])

        candles = gold[gold.index > entry_time]

        for candle_time, candle in candles.iterrows():
            hit_sl = float(candle["high"]) >= stop_loss
            hit_tp = float(candle["low"]) <= take_profit

            if hit_sl and hit_tp:
                trade["status"] = "AMBIGUOUS"
                trade["exit_time"] = candle_time.isoformat()
                changed = True
                break

            if hit_sl:
                trade["status"] = "LOSS"
                trade["exit_time"] = candle_time.isoformat()
                trade["exit_price"] = stop_loss
                trade["outcome_r"] = -1.0
                changed = True
                break

            if hit_tp:
                trade["status"] = "WIN"
                trade["exit_time"] = candle_time.isoformat()
                trade["exit_price"] = take_profit
                trade["outcome_r"] = float(trade["reward_risk"])
                changed = True
                break

    if changed:
        save_journal(journal)

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
    now_utc = pd.Timestamp.now(tz="UTC")
    latest_open = gold.index[-1]
    latest_close = latest_open + pd.Timedelta(minutes=15)
    if now_utc < latest_close:
            gold = gold.iloc[:-1].copy()
    if gold.empty:
                raise RuntimeError("No completed M15 candles are available.")
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

BIQUOTE_PRICE_URL = "https://biquote.io/api/XAUUSD"

BIQUOTE_CALENDAR_URL = (
    "https://biquote.io/api/calendar/upcoming"
    "?countries=US"
    "&importance=high"
    "&limit=20"
)

VERY_HIGH_GOLD_EVENTS = [
    "cpi",
    "core cpi",
    "nonfarm payroll",
    "unemployment rate",
    "fomc",
    "federal reserve",
    "fed interest rate",
    "interest rate decision",
    "powell",
    "pce",
]

HIGH_GOLD_EVENTS = [
    "initial jobless claims",
    "ism manufacturing",
    "ism non-manufacturing",
    "services pmi",
    "manufacturing pmi",
    "crude oil stocks",
    "retail sales",
    "gdp",
]

def _biquote_fetch_quote() -> dict:
    with urllib.request.urlopen(
        BIQUOTE_PRICE_URL,
        timeout=10,
    ) as response:
        data = json.loads(
            response.read().decode("utf-8")
        )

    return {
        "mid": float(data["mid"]),
        "spread": float(data["spread"]),
        "timestamp": data.get("timestamp"),
    }

def _biquote_analyse_quotes(quotes: list[dict]) -> dict:
    moves = [
        current["mid"] - previous["mid"]
        for previous, current in zip(quotes, quotes[1:])
    ]

    up_moves = [move for move in moves if move > 0]
    down_moves = [abs(move) for move in moves if move < 0]

    buy_magnitude = sum(up_moves)
    sell_magnitude = sum(down_moves)
    total_magnitude = buy_magnitude + sell_magnitude

    if total_magnitude > 0:
        buy_pressure = 100 * buy_magnitude / total_magnitude
        sell_pressure = 100 * sell_magnitude / total_magnitude
    else:
        buy_pressure = 0.0
        sell_pressure = 0.0

    velocity = (
        total_magnitude / len(moves)
        if moves else 0.0
    )

    return {
        "buy_pressure": buy_pressure,
        "sell_pressure": sell_pressure,
        "velocity": velocity,
    }

def _biquote_market_state() -> dict:
    windows = []

    for _ in range(3):
        quotes = []

        for sample in range(20):
            try:
                quotes.append(_biquote_fetch_quote())
            except Exception as exc:
                print(
                    f"Biquote quote error: "
                    f"{type(exc).__name__}: {exc}"
                )

            if sample < 19:
                time.sleep(1)

        if len(quotes) < 6:
            raise RuntimeError(
                "Not enough Biquote quotes"
            )

        windows.append(
            _biquote_analyse_quotes(quotes)
        )

    velocities = [
        window["velocity"]
        for window in windows
    ]

    first_velocity = velocities[0]
    last_velocity = velocities[-1]

    if first_velocity > 0:
        velocity_change = (
            (last_velocity - first_velocity)
            / first_velocity
        ) * 100
    else:
        velocity_change = 0.0

    rising_windows = sum(
        1
        for previous, current
        in zip(velocities, velocities[1:])
        if current > previous
    )

    if (
        rising_windows == 2
        and velocity_change >= 50
    ):
        state = "HIGH BUILDUP"

    elif (
        rising_windows >= 1
        and velocity_change >= 20
    ):
        state = "BUILDING"

    elif velocity_change <= -20:
        state = "COOLING"

    else:
        state = "NORMAL"

    latest = windows[-1]

    return {
        "state": state,
        "velocity_change": velocity_change,
        "buy_pressure": latest["buy_pressure"],
        "sell_pressure": latest["sell_pressure"],
    }

def _biquote_gold_relevance(name: str) -> str:
    text = name.lower()

    if any(
        keyword in text
        for keyword in VERY_HIGH_GOLD_EVENTS
    ):
        return "VERY HIGH"

    if any(
        keyword in text
        for keyword in HIGH_GOLD_EVENTS
    ):
        return "HIGH"

    return "MODERATE"

def _biquote_event_risk(minutes: float, relevance: str) -> str:
    if relevance == "VERY HIGH":
        if minutes <= 30:
            return "IMMINENT"
        if minutes <= 120:
            return "HIGH"
        if minutes <= 360:
            return "WATCH"

    if relevance == "HIGH":
        if minutes <= 15:
            return "IMMINENT"
        if minutes <= 60:
            return "HIGH"
        if minutes <= 180:
            return "WATCH"

    return "NORMAL"

def _biquote_calendar_state() -> dict:
    with urllib.request.urlopen(
        BIQUOTE_CALENDAR_URL,
        timeout=15,
    ) as response:
        events = json.loads(
            response.read().decode("utf-8")
        )

    now_utc = datetime.now(timezone.utc)

    risk_rank = {
        "NORMAL": 0,
        "WATCH": 1,
        "HIGH": 2,
        "IMMINENT": 3,
    }

    overall_risk = "NORMAL"
    nearest_event = None

    for event in events:
        time_text = event.get("time")

        if not time_text:
            continue

        event_time = datetime.fromisoformat(
            time_text.replace("Z", "+00:00")
        )

        minutes = (
            event_time - now_utc
        ).total_seconds() / 60

        if minutes < 0:
            continue

        relevance = _biquote_gold_relevance(
            event.get("name", "")
        )

        risk = _biquote_event_risk(
            minutes,
            relevance,
        )

        if risk_rank[risk] > risk_rank[overall_risk]:
            overall_risk = risk

        if (
            relevance in ("VERY HIGH", "HIGH")
            and (
                nearest_event is None
                or minutes < nearest_event["minutes"]
            )
        ):
            nearest_event = {
                "name": event.get("name", "Unknown"),
                "minutes": minutes,
                "relevance": relevance,
                "risk": risk,
            }

    return {
        "risk": overall_risk,
        "nearest_event": nearest_event,
    }


def calculate_current_setup(api_key: str) -> dict:
    """Rebuild the V9.4 directional hierarchy and its valid-entry threshold."""
    gold = _fresh_gold(api_key)
    try:
        biquote_market = _biquote_market_state()
        biquote_calendar = _biquote_calendar_state()

        print("BIQUOTE PRE-VOLATILITY")
        print(
            f"Market state: "
            f"{biquote_market['state']}"
        )
        print(
            f"Velocity change: "
            f"{biquote_market['velocity_change']:+.2f}%"
        )
        print(
            f"Biquote SELL pressure: "
            f"{biquote_market['sell_pressure']:.2f}%"
        )
        print(
            f"Event risk: "
            f"{biquote_calendar['risk']}"
        )
        nearest_event = biquote_calendar.get("nearest_event")

        if nearest_event:
            print(
                f"Nearest event: "
                f"{nearest_event['name']}"
            )
            print(
                f"Event relevance: "
                f"{nearest_event['relevance']}"
            )
            print(
                f"Event in: "
                f"{nearest_event['minutes']:.0f} minutes"
            )
        else:
            print("Nearest event: None")
    except Exception as exc:
        print(
            f"Biquote unavailable: "
            f"{type(exc).__name__}: {exc}"
        )

        biquote_market = {
            "state": "NORMAL",
            "velocity_change": 0.0,
            "buy_pressure": 0.0,
            "sell_pressure": 0.0,
        }

        biquote_calendar = {
            "risk": "NORMAL",
            "nearest_event": None,
        }


    
    print(f"Latest M15 candle used: {gold.index[-1]}")

    # GitHub has no live Streamlit-uploaded footprint. The V9.4 candle engine
    # explicitly supports footprint=None; candle pressure remains the primary input.
    power = analyze_last_10_candles(gold, footprint=None)
    print("V9.4 10-CANDLE DIAGNOSTIC")
    print(
        power.rows.to_string(
            index=False
        )
    )
    sell_diagnostic = diagnose_sell_quality(power)

    print("V9.4 SELL QUALITY DIAGNOSTIC")
    print(
        f"Status: "
        f"{sell_diagnostic['status']}"
    )
    print(
        f"Checks passed: "
        f"{sell_diagnostic['checks_passed']}/"
        f"{sell_diagnostic['checks_total']}"
    )
    print(
        f"SELL candles: "
        f"{sell_diagnostic['sell_count_10']}/10"
    )
    print(
        f"Recent 5 SELL: "
        f"{sell_diagnostic['sell_count_5']}/5"
    )
    print(
        f"Latest 2 SELL: "
        f"{sell_diagnostic['sell_count_2']}/2"
    )
    print(
        f"Failed checks: "
        f"{sell_diagnostic['reasons']}"
    )
    early_sell = detect_early_sell(gold)
    perpetual = collect_free_perpetual_consensus()

    reversal = {"current_signal": 0, "status": "NOT NEEDED"}
    mother = mother_candle_breakout(gold)
    trend = short_term_technical_trend(gold)

    # V9.4 SELL-only mode:
    # the last 10 completed M15 candles remain the sole direction engine.
    # Other modules remain diagnostic only and cannot create or veto direction.
    print("V9.4 10-CANDLE POWER")
    print(f"BUY power: {power.buy_power * 100:.0f}%")
    print(f"SELL power: {power.sell_power * 100:.0f}%")
    print(f"Pressure acceleration: {power.pressure_acceleration * 100:+.0f}%")
    print(f"10-candle signal: {power.signal}")

    if power.signal == "SELL":
        side = "SELL"
        basis = "10-candle power"
    else:
        side = "WAIT"
        basis = "SELL-only mode: no SELL signal"

    result = {
        "side": side,
        "basis": basis,
        "model_time": gold.index[-1].isoformat(),
        "entry_reference": float(gold.close.iloc[-1]),
        "buy_power": float(power.buy_power),
        "sell_power": float(power.sell_power),
        "threshold": None,
        "sell_quality_status": sell_diagnostic["status"],
        "sell_quality_score": sell_diagnostic["score"],
        "sell_quality_checks_passed": sell_diagnostic["checks_passed"],
        "sell_quality_checks_total": sell_diagnostic["checks_total"],
        "sell_candles_10": sell_diagnostic["sell_count_10"],
        "sell_candles_5": sell_diagnostic["sell_count_5"],
        "sell_candles_2": sell_diagnostic["sell_count_2"],
        "pressure_acceleration": float(power.pressure_acceleration),
        "structure_reason": "no directional setup",
    }
    # Hard event-risk gate:
    # Keep the 10-candle signal for diagnostics, but do not
    # permit a new active entry while event risk is IMMINENT.
    if (
        side == "SELL"
        and biquote_calendar["risk"] == "IMMINENT"
    ):
        result["side"] = "WAIT"
        result["basis"] = (
            "SELL signal blocked: imminent economic event"
        )
        result["structure_reason"] = (
            "ENTRY BLOCKED — event risk IMMINENT"
        )

        print(
            "ENTRY BLOCKED: "
            "IMMINENT ECONOMIC EVENT"
        )
        print(
            f"Raw 10-candle SELL power: "
            f"{power.sell_power * 100:.2f}%"
        )

        return result
    if side != "SELL":
        return result

    entry = current_gold_price(api_key)
    print(f"Fresh XAU/USD SELL entry price: {entry:.2f}")
    market_score = {
        "COOLING": 0,
        "NORMAL": 0,
        "BUILDING": 1,
        "HIGH BUILDUP": 2,
    }.get(biquote_market["state"], 0)

    event_score = {
        "NORMAL": 0,
        "WATCH": 1,
        "HIGH": 2,
        "IMMINENT": 3,
    }.get(biquote_calendar["risk"], 0)

    prevolatility_score = market_score + event_score

    if prevolatility_score >= 4:
        prevolatility_state = "EXTREME"
        adaptive_atr_multiple = EXTREME_ATR_MULTIPLE
    elif prevolatility_score >= 3:
        prevolatility_state = "HIGH"
        adaptive_atr_multiple = HIGH_ATR_MULTIPLE
    elif prevolatility_score >= 2:
        prevolatility_state = "BUILDING"
        adaptive_atr_multiple = BUILDING_ATR_MULTIPLE
    else:
        prevolatility_state = "NORMAL"
        adaptive_atr_multiple = STOP_ATR_MULTIPLE

    print(
        f"Combined pre-volatility: "
        f"{prevolatility_state}"
    )
    print(
        f"Adaptive ATR multiplier: "
        f"{adaptive_atr_multiple:.2f}x"
    )
    plan = structure_atr_plan(
        side,
        gold,
        atr_multiple=adaptive_atr_multiple,
        min_tp1_rr=MIN_RR,
        swing_lookback=SWING_LOOKBACK,
        cost_bps=COST_BPS,
        entry_price=entry,
    )

    stop_loss = float(plan.get("stop", np.nan))
    swing_high = float(plan.get("swing", np.nan))
    atr14 = float(plan.get("atr", np.nan))
    atr_buffer = adaptive_atr_multiple * atr14
    stop_distance_detail = abs(entry - stop_loss)

    if not np.isfinite(stop_loss):
        result["structure_reason"] = "No valid structure/ATR stop loss"
        return result

    stop_distance = abs(entry - stop_loss)
    
    if stop_distance <= 0:
        result["structure_reason"] = "Invalid stop-loss distance"
        return result
    
    take_profit = entry - (MIN_RR * stop_distance)
    
    result["entry_reference"] = entry
    result["threshold"] = entry
    result["stop_loss"] = stop_loss
    result["take_profit"] = take_profit
    result["reward_risk"] = MIN_RR
    result["swing_high"] = swing_high
    result["atr14"] = atr14
    result["atr_buffer"] = atr_buffer
    result["stop_distance"] = stop_distance_detail
    result["atr_multiple"] = adaptive_atr_multiple
    result["prevolatility_state"] = prevolatility_state
    result["biquote_market_state"] = biquote_market["state"]
    result["biquote_sell_pressure"] = biquote_market["sell_pressure"]
    result["biquote_velocity_change"] = biquote_market["velocity_change"]
    result["biquote_event_risk"] = biquote_calendar["risk"]
    result["biquote_nearest_event"] = biquote_calendar["nearest_event"]
    result["structure_reason"] = (
            "10-candle SELL power + mandatory structure/ATR SL + 2R TP"
    )

    return result
  


def check_once() -> str:
    api_key = _secret("TWELVE_DATA_API_KEY")
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing.")
    gold_for_outcomes = _fresh_gold(api_key)
    update_open_trades(gold_for_outcomes)
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
    reached = True

    # Deduplicate by completed M15 model candle + side + rounded threshold.
    alert_key = f"{setup['model_time']}|{side}"
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
            and (
                (side == "BUY" and stop_loss < current_price < take_profit)
                or
                (side == "SELL" and take_profit < current_price < stop_loss)
            )
        )
    nearest_event = setup.get("biquote_nearest_event")

    if nearest_event:
        nearest_event_text = (
            f"Nearest event: {nearest_event['name']}\n"
            f"Event relevance: {nearest_event['relevance']}\n"
            f"Event in: {nearest_event['minutes']:.0f} minutes\n"
        )
    else:
        nearest_event_text = "Nearest event: None\n"
    if active:
            message = (
                "Gold Version 9.4 — ACTIVE ENTRY\n"
                f"DIRECTION: {side}\n"
                f"Entry: USD {current_price:,.2f}\n"
                f"Stop loss: USD {stop_loss:,.2f}\n"
                f"Take profit: USD {take_profit:,.2f}\n"
                f"Reward/risk: {reward_risk:.2f}R\n\n"
                "SL DETAILS\n"
                f"Confirmed swing high: USD {setup['swing_high']:,.2f}\n"
                f"ATR14: USD {setup['atr14']:,.2f}\n"
                f"ATR buffer ({setup['atr_multiple']:.2f}x): USD {setup['atr_buffer']:,.2f}\n"
                f"Stop distance: USD {setup['stop_distance']:,.2f}\n\n"
                f"Pre-volatility: {setup['prevolatility_state']}\n"
                f"Biquote market: {setup['biquote_market_state']}\n"
                f"Biquote SELL pressure: {setup['biquote_sell_pressure']:.2f}%\n"
                f"Velocity change: {setup['biquote_velocity_change']:+.2f}%\n"
                f"Event risk: {setup['biquote_event_risk']}\n\n"
                f"{nearest_event_text}\n"
                f"SELL power: {setup['sell_power'] * 100:.2f}%\n"
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
            if active:
                journal = load_journal()
                journal.append({
                    "model_time": setup["model_time"],
                    "side": side,
                    "entry": round(current_price, 4),
                    "stop_loss": round(stop_loss, 4),
                    "take_profit": round(take_profit, 4),
                    "reward_risk": round(reward_risk, 2),
                    "buy_power": round(float(setup["buy_power"]), 4),
                    "sell_power": round(float(setup["sell_power"]), 4),
                    "sell_quality_status": setup["sell_quality_status"],
                    "sell_quality_score": setup["sell_quality_score"],
                    "sell_quality_checks_passed": setup["sell_quality_checks_passed"],
                    "sell_quality_checks_total": setup["sell_quality_checks_total"],
                    "sell_candles_10": setup["sell_candles_10"],
                    "sell_candles_5": setup["sell_candles_5"],
                    "sell_candles_2": setup["sell_candles_2"],
                    "pressure_acceleration": round(float(setup["pressure_acceleration"]), 4),
                    "basis": setup["basis"],
                    "status": "OPEN",
                })
                save_journal(journal)
    
    save_state(state)
    return f"{delivery.status}: {delivery.detail}"

    save_state(state)
    return (
        f"WATCHING {side}: XAU/USD {current_price:,.2f}; "
        f"threshold {threshold:,.2f}; reached={reached}; basis={setup['basis']}"
    )


if __name__ == "__main__":
    print(check_once())
