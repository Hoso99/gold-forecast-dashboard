"""Read-only C2 Raw activation preflight on the V9.5 research runner.

No secrets, no service mutations, no source database writes.
"""
import json,os,subprocess
from pathlib import Path
OUT=Path("v95-c2-activation-preflight.json")
roots=[Path("/home/v95research"),Path("/home/ubuntu/v95-historical-research/derived"),Path("/home/ubuntu/v95-private-export/research"),Path("/home/ubuntu/v95-detector-dev/research")]
def names(base):
    try:
        return sorted(p.name for p in base.iterdir() if any(k in p.name.lower() for k in ("c2","paper","exit","reversal","monitor")))[:50]
    except (PermissionError,OSError) as e:return {"error":type(e).__name__}
def cmd(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=8)
        return {"returncode":p.returncode,"lines":[line[:180] for line in p.stdout.splitlines()[:80]]}
    except (OSError,subprocess.TimeoutExpired) as e:return {"error":type(e).__name__}
services=cmd(["systemctl","list-units","--type=service","--all","--no-pager","--plain"])
if isinstance(services.get("lines"),list):
    services["lines"]=[line for line in services["lines"] if any(x in line.lower() for x in ("v95","research","paper","c2","runner"))]
out={"research_only":True,"action":"READ_ONLY_PREFLIGHT","runner_user":os.getenv("USER"),
     "candidate_file_names":{str(p):names(p) for p in roots},
     "service_name_matches":services,
     "frozen_c2_report_exists":Path("/home/ubuntu/v95-historical-research/derived/c2_raw_vs_scenario_2025_2026_v1.json").is_file(),
     "deployment_changed":False,
     "requirements":["Identify exact running V9.5 PAPER entrypoint and deployment mechanism",
       "Identify verified frozen C2 Raw executable formula (not scenario summary)",
       "Create rollback snapshot and tests before any service restart",
       "Preserve mandatory SL/TP and risk rules; do not modify V9.4 LIVE"]}
OUT.write_text(json.dumps(out,indent=2)+"\n")
print("V95_C2_ACTIVATION_PREFLIGHT_COMPLETE")
print("C2_REPORT_PRESENT",out["frozen_c2_report_exists"])
print("SERVICE_MATCHES",len(services.get("lines",[])))
print("NO_CHANGES_MADE")
