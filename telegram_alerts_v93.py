"""Telegram delivery for Version 9.3 research alerts."""
from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class TelegramDelivery:
    status: str
    detail: str


def build_telegram_alert(*, as_of, expiry, assumption, assumption_status,
                         validated_action, entry, stop_loss, take_profit,
                         reward_risk, pressure, pressure_agreement,
                         event_lock, risk_status, confidence):
    """Build a concise plain-text alert with an explicit validation boundary."""
    released = validated_action in {"BUY", "SELL"} and risk_status == "ACTIVE"
    headline = (
        f"VALIDATED {validated_action}" if released else
        f"{assumption} — ASSUMPTION ONLY")
    position = "CALCULATED POSITION ACTIVE" if released else "POSITION SIZE: ZERO"
    event = "ACTIVE — DO NOT ENTER" if event_lock else "CLEAR"
    return "\n".join([
        "Gold Version 9.3 — 30-minute alert",
        headline,
        f"Model time: {as_of:%Y-%m-%d %H:%M UTC}",
        f"Signal expiry: {expiry:%Y-%m-%d %H:%M UTC}",
        f"Assumption status: {assumption_status}",
        f"Confidence: {confidence}",
        f"Market pressure: {pressure} ({pressure_agreement})",
        f"Entry reference: USD {entry:,.2f}",
        f"Stop loss: USD {stop_loss:,.2f}",
        f"Take profit: USD {take_profit:,.2f}",
        f"Reward:risk: {reward_risk:.2f}:1",
        f"Event lock: {event}",
        position,
        "Research alert only. Stops can slip; no order was submitted.",
    ])


def send_telegram_alert(bot_token, chat_id, message, timeout=8.0):
    """Send one Telegram message; configuration or network failure is nonfatal."""
    token = str(bot_token or "").strip()
    destination = str(chat_id or "").strip()
    if not token or not destination:
        return TelegramDelivery(
            "NOT CONFIGURED",
            "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to Streamlit secrets.")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urlencode({"chat_id": destination, "text": message,
                        "disable_web_page_preview": "true"}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "Gold-Version-9.3/1.0"},
        method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return TelegramDelivery("FAILED", f"Telegram HTTP {exc.code}")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return TelegramDelivery("FAILED", str(exc))
    if not payload.get("ok"):
        return TelegramDelivery("FAILED", str(payload.get("description", "unknown error")))
    return TelegramDelivery("SENT", "Telegram alert delivered.")
