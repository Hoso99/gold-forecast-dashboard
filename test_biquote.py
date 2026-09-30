import json
import time
import urllib.request
from datetime import datetime, timezone

URL = "https://biquote.io/api/XAUUSD"

WINDOWS = 3
SAMPLES_PER_WINDOW = 20
INTERVAL_SECONDS = 1

all_windows = []


def get_quote():
    with urllib.request.urlopen(URL, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))

    return {
        "mid": float(data["mid"]),
        "bid": float(data["bid"]),
        "ask": float(data["ask"]),
        "spread": float(data["spread"]),
        "timestamp": data.get("timestamp"),
    }


def analyse_window(quotes):
    moves = [
        current["mid"] - previous["mid"]
        for previous, current in zip(quotes, quotes[1:])
    ]

    up_moves = [move for move in moves if move > 0]
    down_moves = [abs(move) for move in moves if move < 0]

    up_ticks = len(up_moves)
    down_ticks = len(down_moves)
    flat_ticks = sum(1 for move in moves if move == 0)

    directional_ticks = up_ticks + down_ticks

    if directional_ticks:
        buy_tick_pressure = (
            up_ticks / directional_ticks
        ) * 100
        sell_tick_pressure = (
            down_ticks / directional_ticks
        ) * 100
    else:
        buy_tick_pressure = 0.0
        sell_tick_pressure = 0.0

    buy_magnitude = sum(up_moves)
    sell_magnitude = sum(down_moves)
    total_magnitude = buy_magnitude + sell_magnitude

    if total_magnitude:
        buy_magnitude_pressure = (
            buy_magnitude / total_magnitude
        ) * 100
        sell_magnitude_pressure = (
            sell_magnitude / total_magnitude
        ) * 100
    else:
        buy_magnitude_pressure = 0.0
        sell_magnitude_pressure = 0.0

    velocity = (
        total_magnitude / len(moves)
        if moves else 0.0
    )

    net_change = quotes[-1]["mid"] - quotes[0]["mid"]

    average_spread = (
        sum(q["spread"] for q in quotes) / len(quotes)
    )

    return {
        "up_ticks": up_ticks,
        "down_ticks": down_ticks,
        "flat_ticks": flat_ticks,
        "buy_tick_pressure": buy_tick_pressure,
        "sell_tick_pressure": sell_tick_pressure,
        "buy_magnitude_pressure": buy_magnitude_pressure,
        "sell_magnitude_pressure": sell_magnitude_pressure,
        "velocity": velocity,
        "net_change": net_change,
        "average_spread": average_spread,
    }


print("Biquote XAU/USD — MULTI-WINDOW PRE-VOLATILITY TEST")
print(
    f"{WINDOWS} windows x "
    f"{SAMPLES_PER_WINDOW} samples\n"
)

for window_number in range(1, WINDOWS + 1):

    quotes = []

    print(f"--- WINDOW {window_number} ---")

    for sample in range(SAMPLES_PER_WINDOW):

        try:
            quote = get_quote()
            quotes.append(quote)

            print(
                f"{sample + 1:02d} | "
                f"Mid {quote['mid']:.3f} | "
                f"Spread {quote['spread']:.3f}"
            )

        except Exception as exc:
            print(
                f"{sample + 1:02d} | ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

        if not (
            window_number == WINDOWS
            and sample == SAMPLES_PER_WINDOW - 1
        ):
            time.sleep(INTERVAL_SECONDS)

    if len(quotes) < 6:
        raise RuntimeError(
            f"Not enough quotes in window {window_number}"
        )

    result = analyse_window(quotes)
    all_windows.append(result)

    print(
        f"\nWindow {window_number} result:"
    )
    print(
        f"BUY/SELL tick pressure: "
        f"{result['buy_tick_pressure']:.2f}% / "
        f"{result['sell_tick_pressure']:.2f}%"
    )
    print(
        f"BUY/SELL magnitude: "
        f"{result['buy_magnitude_pressure']:.2f}% / "
        f"{result['sell_magnitude_pressure']:.2f}%"
    )
    print(
        f"Velocity: {result['velocity']:.4f}"
    )
    print(
        f"Net change: {result['net_change']:+.3f}"
    )
    print(
        f"Average spread: "
        f"{result['average_spread']:.3f}\n"
    )


velocities = [
    result["velocity"]
    for result in all_windows
]

first_velocity = velocities[0]
last_velocity = velocities[-1]

if first_velocity > 0:
    velocity_change_pct = (
        (last_velocity - first_velocity)
        / first_velocity
    ) * 100
else:
    velocity_change_pct = 0.0

rising_windows = sum(
    1
    for previous, current
    in zip(velocities, velocities[1:])
    if current > previous
)

latest = all_windows[-1]

dominant_pressure = max(
    latest["buy_magnitude_pressure"],
    latest["sell_magnitude_pressure"],
)

if latest["buy_magnitude_pressure"] > latest["sell_magnitude_pressure"]:
    dominant_side = "BUY"
else:
    dominant_side = "SELL"

if (
    rising_windows == WINDOWS - 1
    and velocity_change_pct >= 50
):
    pre_volatility_state = "HIGH BUILDUP"

elif (
    rising_windows >= 1
    and velocity_change_pct >= 20
):
    pre_volatility_state = "BUILDING"

elif velocity_change_pct <= -20:
    pre_volatility_state = "COOLING"

else:
    pre_volatility_state = "NORMAL"


print("\n========== FINAL RESULT ==========")

for number, result in enumerate(all_windows, start=1):
    print(
        f"Window {number} velocity: "
        f"{result['velocity']:.4f}"
    )

print(
    f"Velocity change first→last: "
    f"{velocity_change_pct:+.2f}%"
)

print(
    f"Rising velocity windows: "
    f"{rising_windows}/{WINDOWS - 1}"
)

print(
    f"Latest dominant pressure: "
    f"{dominant_side} {dominant_pressure:.2f}%"
)

print(
    f"PRE-VOLATILITY STATE: "
    f"{pre_volatility_state}"
)

print(
    f"Test completed: "
    f"{datetime.now(timezone.utc).isoformat()}"
)
