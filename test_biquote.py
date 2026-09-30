import json
import time
import urllib.request
from datetime import datetime, timezone

URL = "https://biquote.io/api/XAUUSD"

SAMPLES = 30
INTERVAL_SECONDS = 1

quotes = []

print("Biquote XAU/USD — 30-second tick pressure test")
print(f"Collecting {SAMPLES} samples...\n")

for i in range(SAMPLES):
    try:
        with urllib.request.urlopen(URL, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))

        mid = float(data["mid"])
        bid = float(data["bid"])
        ask = float(data["ask"])
        spread = float(data["spread"])

        quotes.append({
            "mid": mid,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "timestamp": data.get("timestamp"),
        })

        print(
            f"{i + 1:02d} | "
            f"Mid {mid:.3f} | "
            f"Bid {bid:.3f} | "
            f"Ask {ask:.3f} | "
            f"Spread {spread:.3f}"
        )

    except Exception as exc:
        print(f"{i + 1:02d} | ERROR: {type(exc).__name__}: {exc}")

    if i < SAMPLES - 1:
        time.sleep(INTERVAL_SECONDS)

if len(quotes) < 2:
    raise RuntimeError("Not enough valid quotes to calculate pressure.")

up_ticks = 0
down_ticks = 0
flat_ticks = 0

for previous, current in zip(quotes, quotes[1:]):
    if current["mid"] > previous["mid"]:
        up_ticks += 1
    elif current["mid"] < previous["mid"]:
        down_ticks += 1
    else:
        flat_ticks += 1

directional_ticks = up_ticks + down_ticks

if directional_ticks:
    buy_pressure = (up_ticks / directional_ticks) * 100
    sell_pressure = (down_ticks / directional_ticks) * 100
else:
    buy_pressure = 0.0
    sell_pressure = 0.0

start_price = quotes[0]["mid"]
end_price = quotes[-1]["mid"]
price_change = end_price - start_price

average_spread = sum(q["spread"] for q in quotes) / len(quotes)

unique_timestamps = len(
    {q["timestamp"] for q in quotes if q["timestamp"] is not None}
)

print("\n========== RESULT ==========")
print(f"Valid samples: {len(quotes)}")
print(f"UP ticks: {up_ticks}")
print(f"DOWN ticks: {down_ticks}")
print(f"FLAT ticks: {flat_ticks}")
print(f"BUY tick pressure: {buy_pressure:.2f}%")
print(f"SELL tick pressure: {sell_pressure:.2f}%")
print(f"Start mid: {start_price:.3f}")
print(f"End mid: {end_price:.3f}")
print(f"Net price change: {price_change:+.3f}")
print(f"Average spread: {average_spread:.3f}")
print(f"Unique quote timestamps: {unique_timestamps}/{len(quotes)}")
print(f"Test completed: {datetime.now(timezone.utc).isoformat()}")
