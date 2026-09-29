"""Gold V9.4 valid-entry threshold watcher."""
from __future__ import annotations
import json, os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from telegram_alerts_v93 import send_telegram_alert

STATE_FILE = Path(os.getenv("V94_ENTRY_WATCH_STATE", "entry_watch_v94.json"))
TWELVE_DATA_URL = "https://api.twelvedata.com/price"

def _secret(name):
    value = str(os.getenv(name, "") or "").strip()
    if value:
        return value
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""

def latest_xauusd_price(api_key):
    if not api_key:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing.")
    query = urlencode({"symbol": "XAU/USD", "apikey": api_key})
    try:
        with urlopen(f"{TWELVE_DATA_URL}?{query}", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Twelve Data HTTP {exc.code}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Twelve Data request failed: {exc}") from exc
    if payload.get("status") == "error":
        raise RuntimeError(f"Twelve Data error: {payload.get('message', 'unknown error')}")
    try:
        price = float(payload["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Twelve Data returned no valid XAU/USD price.") from exc
    if price <= 0:
        raise RuntimeError("Twelve Data returned an invalid XAU/USD price.")
    return price

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

def threshold_reached(side, price, threshold):
    side = side.upper()
    return price <= threshold if side == "BUY" else price >= threshold if side == "SELL" else False

def check_once():
    state = load_state()
    side = str(state.get("side", "")).upper()
    try:
        threshold = float(state.get("threshold"))
    except (TypeError, ValueError):
        threshold = float("nan")
    if side not in {"BUY", "SELL"} or not (threshold > 0):
        return "NO VALID ENTRY THRESHOLD SAVED"

    price = latest_xauusd_price(_secret("TWELVE_DATA_API_KEY"))
    reached = threshold_reached(side, price, threshold)
    threshold_key = f"{side}:{threshold:.4f}"
    if state.get("threshold_key") != threshold_key:
        state["threshold_key"] = threshold_key
        state["alerted"] = False

    if reached and not bool(state.get("alerted", False)):
        condition = "at or below" if side == "BUY" else "at or above"
        message = (
            "Gold Version 9.4 — ENTRY THRESHOLD REACHED\n"
            f"{side} threshold reached\n"
            f"Current XAU/USD: USD {price:,.2f}\n"
            f"Valid-entry threshold: {condition} USD {threshold:,.2f}\n"
            "REVALIDATE V9.4 NOW for a fresh stop loss, take profit and >=2R check.\n"
            "Threshold alert only. No order was submitted."
        )
        delivery = send_telegram_alert(
            _secret("TELEGRAM_BOT_TOKEN"), _secret("TELEGRAM_CHAT_ID"), message)
        if delivery.status == "SENT":
            state["alerted"] = True
            state["last_alert_price"] = price
            save_state(state)
        return f"{delivery.status}: {delivery.detail}"

    save_state(state)
    return f"WATCHING {side}: XAU/USD {price:,.2f}; threshold {threshold:,.2f}; reached={reached}"

if __name__ == "__main__":
    print(check_once())
