import json
import urllib.request

URL = "https://biquote.io/api/XAUUSD"

print("Testing biquote XAU/USD feed...")
print(f"URL: {URL}")

try:
    with urllib.request.urlopen(URL, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    print("\nSUCCESS")
    print(json.dumps(data, indent=2))

except Exception as exc:
    print("\nFAILED")
    print(type(exc).__name__, str(exc))
