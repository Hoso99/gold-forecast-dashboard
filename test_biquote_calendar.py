import json
import urllib.request
from datetime import datetime, timezone

URL = (
    "https://biquote.io/api/calendar/upcoming"
    "?countries=US"
    "&importance=high"
    "&limit=20"
)

print("Biquote — High-Impact US Economic Calendar Test")
print(f"Requesting: {URL}\n")

try:
    with urllib.request.urlopen(URL, timeout=15) as response:
        data = json.loads(
            response.read().decode("utf-8")
        )

    print("HTTP request: SUCCESS")
    print(f"Response type: {type(data).__name__}")
    print("\n========== RAW RESPONSE ==========")
    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        )
    )

    print("\n========== TEST TIME ==========")
    print(datetime.now(timezone.utc).isoformat())

except Exception as exc:
    print(
        f"FAILED: {type(exc).__name__}: {exc}"
    )
    raise
