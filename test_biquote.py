import json
import time
import urllib.request
from datetime import datetime, timezone

URL = "https://biquote.io/api/XAUUSD"

SAMPLES = 30
INTERVAL_SECONDS = 1

quotes = []

print("Biquote XAU/USD — pressure + magnitude + acceleration test")
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

if len(quotes) < 6:
    raise RuntimeError("Not enough valid quotes to calculate pressure.")

moves = []

for previous, current in zip(quotes, quotes[1:]):
    moves.append(current["mid"] - previous["mid"])

up_moves = [move for move in moves if move > 0]
down_moves = [abs(move) for move in moves if move < 0]
flat_ticks = sum(1 for move in moves if move == 0)

up_ticks = len(up_moves)
down_ticks = len(down_moves)

directional_ticks = up_ticks + down_ticks

if directional_ticks:
    buy_tick_pressure = (up_ticks / directional_ticks) * 100
    sell_tick_pressure = (down_ticks / directional_ticks) * 100
else:
    buy_tick_pressure = 0.0
    sell_tick_pressure = 0.0

buy_magnitude = sum(up_moves)
sell_magnitude = sum(down_moves)

total_magnitude = buy_magnitude + sell_magnitude

if total_magnitude:
    buy_magnitude_pressure = (buy_magnitude / total_magnitude) * 100
    sell_magnitude_pressure = (sell_magnitude / total_magnitude) * 100
else:
    buy_magnitude_pressure = 0.0
    sell_magnitude_pressure = 0.0

absolute_moves = [abs(move) for move in moves]

half = len(absolute_moves) // 2

first_half = absolute_moves[:half]
second_half = absolute_moves[half:]

first_velocity = (
    sum(first_half) / len(first_half)
    if first_half else 0.0
)

second_velocity = (
    sum(second_half) / len(second_half)
    if second_half else 0.0
)

if first_velocity > 0:
    acceleration_pct = (
        (second_velocity - first_velocity) / first_velocity
    ) * 100
else:
    acceleration_pct = 0.0

if acceleration_pct >= 50:
    volatility_state = "HIGH BUILDUP"
elif acceleration_pct >= 20:
    volatility_state = "BUILDING"
elif acceleration_pct <= -20:
    volatility_state = "COOLING"
else:
    volatility_state = "NORMAL"

start_price = quotes[0]["mid"]
end_price = quotes[-1]["mid"]
net_change = end_price - start_price

average_spread = (
    sum(q["spread"] for q in quotes) / len(quotes)
)

unique_timestamps = len(
    {q["timestamp"] for q in quotes if q["timestamp"] is not None}
)

print("\n========== RESULT ==========")

print(f"Valid samples: {len(quotes)}")
print(f"UP ticks: {up_ticks}")
print(f"DOWN ticks: {down_ticks}")
print(f"FLAT ticks: {flat_ticks}")

print(f"BUY tick pressure: {buy_tick_pressure:.2f}%")
print(f"SELL tick pressure: {sell_tick_pressure:.2f}%")

print(f"BUY move magnitude: {buy_magnitude:.3f}")
print(f"SELL move magnitude: {sell_magnitude:.3f}")

print(
    f"BUY magnitude pressure: "
    f"{buy_magnitude_pressure:.2f}%"
)

print(
    f"SELL magnitude pressure: "
    f"{sell_magnitude_pressure:.2f}%"
)

print(f"Early move velocity: {first_velocity:.4f}")
print(f"Recent move velocity: {second_velocity:.4f}")
print(f"Pressure acceleration: {acceleration_pct:+.2f}%")

print(f"VOLATILITY STATE: {volatility_state}")

print(f"Start mid: {start_price:.3f}")
print(f"End mid: {end_price:.3f}")
print(f"Net price change: {net_change:+.3f}")

print(f"Average spread: {average_spread:.3f}")

print(
    f"Unique quote timestamps: "
    f"{unique_timestamps}/{len(quotes)}"
)

print(
    f"Test completed: "
    f"{datetime.now(timezone.utc).isoformat()}"
)
