"""Download newest completed V9.4 forward M1 collector artifact (research only)."""
import io
import json
import os
import pathlib
import urllib.request
import zipfile

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
           and a.get('workflow_run', {}).get('head_branch') == os.environ.get('GITHUB_REF_NAME', 'main')]
if not matches:
    matches = [a for a in items if not a.get('expired')
               and a.get('name', '').startswith('v94-forward-m1')]
if not matches:
    raise SystemExit('No non-expired v94-forward-m1 artifact found in latest 500 artifacts.')

a = max(matches, key=lambda x: x.get('created_at', ''))
raw = get(a['archive_download_url'])
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names = [n for n in z.namelist() if pathlib.PurePosixPath(n).name == 'v94_forward_m1.csv']
    if len(names) != 1:
        raise SystemExit(f'Expected one v94_forward_m1.csv, got {names}')
    data = z.read(names[0])

out = pathlib.Path('research/v94_stop_comparison/v94_forward_m1.csv')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(data)
print(f"Downloaded collector artifact id={a['id']} created={a['created_at']} rows={len(data.splitlines())-1}")
