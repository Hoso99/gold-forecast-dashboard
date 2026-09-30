import json
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PRICE_URL = "https://biquote.io/api/XAUUSD"

CALENDAR_URL = (
    "https://biquote.io/api/calendar/upcoming"
    "?countries=US"
    "&importance=high"
    "&limit=20"
)

CYPRUS_TZ = ZoneInfo("Europe/Nicosia")

WINDOWS = 3
SAMPLES_PER_WINDOW = 20
INTERVAL_SECONDS = 1


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


def fetch_quote():
    with urllib.request.urlopen(
        PRICE_URL,
        timeout=10
    ) as response:

        data = json.loads(
            response.read().decode("utf-8")
        )

    return {
        "mid": float(data["mid"]),
        "spread": float(data["spread"]),
        "timestamp": data.get("timestamp"),
    }


def analyse_window(quotes):

    moves = [
        current["mid"] - previous["mid"]
        for previous, current
        in zip(quotes, quotes[1:])
    ]

    up_moves = [
        move for move in moves
        if move > 0
    ]

    down_moves = [
        abs(move) for move in moves
        if move < 0
    ]

    buy_magnitude = sum(up_moves)
    sell_magnitude = sum(down_moves)

    total_magnitude = (
        buy_magnitude + sell_magnitude
    )

    if total_magnitude:

        buy_pressure = (
            buy_magnitude /
            total_magnitude
        ) * 100

        sell_pressure = (
            sell_magnitude /
            total_magnitude
        ) * 100

    else:
        buy_pressure = 0.0
        sell_pressure = 0.0

    velocity = (
        total_magnitude / len(moves)
        if moves else 0.0
    )

    average_spread = (
        sum(q["spread"] for q in quotes)
        / len(quotes)
    )

    return {
        "buy_pressure": buy_pressure,
        "sell_pressure": sell_pressure,
        "velocity": velocity,
        "spread": average_spread,
    }


def gold_relevance(name):

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


def event_risk(minutes, relevance):

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


print(
    "Biquote — Combined Gold "
    "Pre-Volatility Test\n"
)


# ---------------------------------
# MARKET ACTIVITY TEST
# ---------------------------------

window_results = []

for window_number in range(
    1,
    WINDOWS + 1
):

    quotes = []

    print(
        f"Collecting market window "
        f"{window_number}/{WINDOWS}..."
    )

    for sample in range(
        SAMPLES_PER_WINDOW
    ):

        try:
            quote = fetch_quote()
            quotes.append(quote)

        except Exception as exc:
            print(
                f"Quote error: "
                f"{type(exc).__name__}: {exc}"
            )

        if not (
            window_number == WINDOWS
            and sample ==
            SAMPLES_PER_WINDOW - 1
        ):
            time.sleep(
                INTERVAL_SECONDS
            )

    if len(quotes) < 6:
        raise RuntimeError(
            "Not enough quotes "
            f"in window {window_number}"
        )

    result = analyse_window(quotes)
    window_results.append(result)

    print(
        f"Window {window_number}: "
        f"velocity "
        f"{result['velocity']:.4f} | "
        f"BUY "
        f"{result['buy_pressure']:.2f}% | "
        f"SELL "
        f"{result['sell_pressure']:.2f}%"
    )


velocities = [
    result["velocity"]
    for result in window_results
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
    in zip(
        velocities,
        velocities[1:]
    )
    if current > previous
)


if (
    rising_windows == WINDOWS - 1
    and velocity_change >= 50
):
    market_state = "HIGH BUILDUP"

elif (
    rising_windows >= 1
    and velocity_change >= 20
):
    market_state = "BUILDING"

elif velocity_change <= -20:
    market_state = "COOLING"

else:
    market_state = "NORMAL"


latest_market = window_results[-1]

if (
    latest_market["buy_pressure"]
    >= 60
):
    directional_bias = "BUY"

elif (
    latest_market["sell_pressure"]
    >= 60
):
    directional_bias = "SELL"

else:
    directional_bias = "MIXED"


# ---------------------------------
# ECONOMIC EVENT TEST
# ---------------------------------

with urllib.request.urlopen(
    CALENDAR_URL,
    timeout=15
) as response:

    events = json.loads(
        response.read().decode("utf-8")
    )


now_utc = datetime.now(
    timezone.utc
)

nearest_relevant_event = None

event_rank = {
    "NORMAL": 0,
    "WATCH": 1,
    "HIGH": 2,
    "IMMINENT": 3,
}

overall_event_risk = "NORMAL"


for event in events:

    time_text = event.get("time")

    if not time_text:
        continue

    event_time = datetime.fromisoformat(
        time_text.replace(
            "Z",
            "+00:00"
        )
    )

    minutes = (
        event_time - now_utc
    ).total_seconds() / 60

    if minutes < 0:
        continue

    relevance = gold_relevance(
        event.get("name", "")
    )

    risk = event_risk(
        minutes,
        relevance
    )

    if (
        event_rank[risk]
        > event_rank[overall_event_risk]
    ):
        overall_event_risk = risk

    if (
        relevance in ("VERY HIGH", "HIGH")
        and (
            nearest_relevant_event is None
            or minutes
            < nearest_relevant_event["minutes"]
        )
    ):
        nearest_relevant_event = {
            "name": event.get(
                "name",
                "Unknown"
            ),
            "time": event_time,
            "minutes": minutes,
            "relevance": relevance,
            "risk": risk,
        }


# ---------------------------------
# COMBINED PRE-VOLATILITY STATE
# ---------------------------------

market_score = {
    "COOLING": 0,
    "NORMAL": 0,
    "BUILDING": 1,
    "HIGH BUILDUP": 2,
}[market_state]

event_score = {
    "NORMAL": 0,
    "WATCH": 1,
    "HIGH": 2,
    "IMMINENT": 3,
}[overall_event_risk]

combined_score = (
    market_score + event_score
)


if combined_score >= 4:
    combined_state = "EXTREME"

elif combined_score >= 3:
    combined_state = "HIGH"

elif combined_score >= 2:
    combined_state = "BUILDING"

else:
    combined_state = "NORMAL"


if combined_state == "NORMAL":
    sl_regime = "STANDARD"

elif combined_state == "BUILDING":
    sl_regime = "MODERATELY WIDER"

elif combined_state == "HIGH":
    sl_regime = "WIDER"

else:
    sl_regime = "EXTREME / REVIEW ENTRY"


# ---------------------------------
# FINAL RESULT
# ---------------------------------

print(
    "\n========== COMBINED RESULT =========="
)

print(
    f"Market state: {market_state}"
)

print(
    f"Velocity change: "
    f"{velocity_change:+.2f}%"
)

print(
    f"Directional pressure: "
    f"{directional_bias}"
)

print(
    f"Latest BUY magnitude: "
    f"{latest_market['buy_pressure']:.2f}%"
)

print(
    f"Latest SELL magnitude: "
    f"{latest_market['sell_pressure']:.2f}%"
)

print(
    f"Event risk: "
    f"{overall_event_risk}"
)


if nearest_relevant_event:

    event = nearest_relevant_event

    cyprus_time = (
        event["time"]
        .astimezone(CYPRUS_TZ)
    )

    print(
        f"Nearest gold event: "
        f"{event['name']}"
    )

    print(
        f"Gold relevance: "
        f"{event['relevance']}"
    )

    print(
        f"Event Cyprus time: "
        f"{cyprus_time.strftime('%Y-%m-%d %H:%M %Z')}"
    )

    print(
        f"Minutes until event: "
        f"{event['minutes']:.0f}"
    )


print(
    f"COMBINED PRE-VOLATILITY: "
    f"{combined_state}"
)

print(
    f"SL/TP REGIME: "
    f"{sl_regime}"
)

print(
    "====================================="
)
