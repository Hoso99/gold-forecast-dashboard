"""Download newest completed V9.4 forward M1 collector artifact via GitHub Actions API."""
import io, json, os, pathlib, urllib.request, zipfile
repo=os.environ['GITHUB_REPOSITORY']
token=os.environ['GH_TOKEN']
headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'v94-research-only'}
def get(url):
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=60) as r:return r.read()
base=f'https://api.github.com/repos/{repo}/actions/artifacts?per_page=100'
items=[]
for page in range(1,6):
    obj=json.loads(get(base+f'&page={page}'))
    items.extend(obj.get('artifacts',[]))
    if len(obj.get('artifacts',[]))<100:break
matches=[a for a in items if not a.get('expired') and a.get('name','').startswith('v94-forward-m1') and a.get('workflow_run',{}).get('head_branch')==os.environ.get('GITHUB_REF_NAME','main')]
# A collector may run on a branch other than the workflow branch: fall back to all branches.
if not matches:matches=[a for a in items if not a.get('expired') and a.get('name','').startswith('v94-forward-m1')]
if not matches:raise SystemExit('No non-expired v94-forward-m1 artifact found in latest 500 artifacts; verify collector workflow/artifact name.')
a=max(matches,key=lambda x:x.get('created_at',''))
raw=get(a['archive_download_url'])
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    names=[n for n in z.namelist() if pathlib.PurePosixPath(n).name=='v94_forward_m1.csv']
    if len(names)!=1:raise SystemExit(f'Expected one v94_forward_m1.csv, got {names}')
    data=z.read(names[0])
pathlib.Path('research/v94_stop_comparison/v94_forward_m1.csv').write_bytes(data)
print(f"Downloaded collector artifact id={a['id']} created={a['created_at']} rows={len(data.splitlines())-1}")
