"""Collect completed Twelve Data XAU/USD M1 candles for frozen V9.4 research.
Does not generate trade signals, place orders, or send Telegram alerts.
"""
import csv
import datetime as dt
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

UTC = dt.timezone.utc
CUTOFF = dt.datetime(2026, 10, 8, 13, 56, tzinfo=UTC)
DEST = Path('research/data/v94_forward_m1.csv')
KEY = os.environ.get('TWELVE_DATA_API_KEY', '').strip()
if not KEY:
    raise SystemExit('Missing TWELVE_DATA_API_KEY secret')

existing = {}
if DEST.exists():
    with DEST.open(newline='') as f:
        for row in csv.DictReader(f):
            existing[row['datetime']] = row

now = dt.datetime.now(UTC)
last = dt.datetime.fromisoformat(max(existing)) if existing else CUTOFF
# Overlap two hours to deduplicate and detect corrections. Each run must be frequent
# enough that the API can cover missed candles; gaps are explicitly reported.
start = max(CUTOFF, last - dt.timedelta(hours=2))
params = {
    'symbol': 'XAU/USD', 'interval': '1min', 'start_date': start.strftime('%Y-%m-%d %H:%M:%S'),
    'end_date': now.strftime('%Y-%m-%d %H:%M:%S'), 'timezone': 'UTC',
    'outputsize': 5000, 'apikey': KEY, 'format': 'JSON'
}
url = 'https://api.twelvedata.com/time_series?' + urlencode(params)
with urlopen(url, timeout=35) as resp:
    payload = json.load(resp)
if payload.get('status') == 'error' or 'values' not in payload:
    raise SystemExit('Twelve Data returned an error: ' + str(payload.get('message', 'no values')))

new = 0
for item in payload['values']:
    ts = dt.datetime.strptime(item['datetime'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=UTC)
    # Twelve Data timestamps are candle STARTS. Keep only fully closed candles.
    if ts <= CUTOFF or ts + dt.timedelta(minutes=1) > now - dt.timedelta(seconds=10):
        continue
    key = ts.isoformat()
    row = {'datetime': key}
    for field in ('open', 'high', 'low', 'close'):
        row[field] = str(float(item[field]))
    if key not in existing:
        new += 1
    existing[key] = row

DEST.parent.mkdir(parents=True, exist_ok=True)
with DEST.open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['datetime', 'open', 'high', 'low', 'close'])
    w.writeheader()
    w.writerows(existing[k] for k in sorted(existing))

keys = sorted(existing)
# Gold is not traded continuously on weekends/holidays; report gaps, do not invent bars.
gaps = []
for a, b in zip(keys, keys[1:]):
    delta = dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)
    if delta > dt.timedelta(minutes=1):
        gaps.append((a, b, str(delta)))
print(f'New completed candles: {new}; total stored: {len(existing)}; observed gaps: {len(gaps)}')
for a, b, gap in gaps[-10:]:
    print(f'GAP {a} -> {b}: {gap} (could be closure or missing data)')
if keys:
    print('First:', keys[0], 'Last:', keys[-1])
