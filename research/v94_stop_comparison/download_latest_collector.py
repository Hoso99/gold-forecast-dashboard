"""Download newest completed V9.4 forward M1 collector artifact (research only)."""
import io
import csv
import json
import os
import pathlib
import urllib.request
import zipfile
from datetime import datetime, timezone

repo = os.environ['GITHUB_REPOSITORY']
token = os.environ['GH_TOKEN']
api_headers = {
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'v94-research-only',
}

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward GitHub API credentials to artifact storage redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith('https://'):
            raise ValueError('Refusing non-HTTPS artifact redirect')
        next_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if next_req is not None:
            next_req.remove_header('Authorization')
            next_req.remove_header('X-GitHub-Api-Version')
            next_req.remove_header('Accept')
        return next_req

opener = urllib.request.build_opener(SafeRedirect())

def get(url):
    if not url.startswith(f'https://api.github.com/repos/{repo}/actions/'):
        raise ValueError('Unexpected GitHub API URL')
    req = urllib.request.Request(url, headers=api_headers)
    with opener.open(req, timeout=60) as response:
        return response.read()

base = f'https://api.github.com/repos/{repo}/actions/artifacts?per_page=100'
items = []
for page in range(1, 6):
    obj = json.loads(get(base + f'&page={page}'))
    batch = obj.get('artifacts', [])
    items.extend(batch)
    if len(batch) < 100:
        break

matches = [a for a in items if not a.get('expired')
           and a.get('name', '').startswith('v94-forward-m1')
           and a.get('workflow_run', {}).get('head_branch') == 'main']
if not matches:
    raise SystemExit('No non-expired main-branch collector artifact in latest 500 artifacts.')

a = max(matches, key=lambda x: x.get('created_at', ''))
created = datetime.fromisoformat(a['created_at'].replace('Z', '+00:00'))
age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
if age_hours < 0 or age_hours > 8:
    raise SystemExit(f'Collector artifact too old or future-dated: {age_hours:.2f}h; maximum 8h')
raw = get(a['archive_download_url'])
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names = [n for n in z.namelist() if pathlib.PurePosixPath(n).name == 'v94_forward_m1.csv']
    if len(names) != 1:
        raise SystemExit(f'Expected one v94_forward_m1.csv, got {names}')
    data = z.read(names[0])

# Validate timestamps inside the artifact, not only its upload time.
rows = list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'))))
if not rows or 'datetime' not in rows[0]:
    raise SystemExit('Collector CSV is empty or missing datetime column')
times = [datetime.fromisoformat(r['datetime'].replace('Z', '+00:00')) for r in rows]
if any(t.tzinfo is None for t in times):
    raise SystemExit('Collector candles must have UTC-aware timestamps')
latest = max(times)
now_utc = datetime.now(timezone.utc)
candle_age_minutes = (now_utc - latest).total_seconds() / 60
# Indicative weekend closure only. Holidays/early closes require separate calendar.
weekend_closed = now_utc.weekday() == 5 or (now_utc.weekday() == 6 and now_utc.hour < 22) or (now_utc.weekday() == 4 and now_utc.hour >= 22)
print(f'Collector latest_candle_utc={latest.isoformat()} candle_age_minutes={candle_age_minutes:.1f} weekend_closed={weekend_closed}')
if candle_age_minutes < 0:
    raise SystemExit('Collector contains a future-dated candle')
if not weekend_closed and candle_age_minutes > 90:
    raise SystemExit(f'Collector M1 candles stale: {candle_age_minutes:.1f} minutes (>90)')
if weekend_closed:
    print('Weekend window: candle-age gate skipped; artifact-age gate remains enforced.')
out = pathlib.Path('research/v94_stop_comparison/v94_forward_m1.csv')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(data)
print(f"Downloaded collector artifact id={a['id']} created={a['created_at']} age_hours={age_hours:.2f} rows={len(data.splitlines())-1} collector_branch=main")
