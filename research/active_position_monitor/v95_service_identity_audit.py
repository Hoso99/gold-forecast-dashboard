"""Read-only V9.5 service identity check; never inspect service environment.

Only reports non-secret systemd identity fields and current runner identity.
Does not use sudo, modify permissions, read trade history, or restart services.
"""
import json
import os
import pwd
import subprocess

def inspect():
    report={"runner_user":pwd.getpwuid(os.geteuid()).pw_name,
            "service":"v95-research-monitor.service"}
    try:
        result=subprocess.run(
            ["systemctl","show","v95-research-monitor.service",
             "--property=User,Group,LoadState,ActiveState,FragmentPath",
             "--no-pager"],
            capture_output=True,text=True,timeout=8,check=False)
        if result.returncode:
            report["service_query"]="UNAVAILABLE"
            return report
        fields={}
        for line in result.stdout.splitlines():
            if "=" in line:
                key,value=line.split("=",1)
                if key in {"User","Group","LoadState","ActiveState","FragmentPath"}:
                    fields[key]=value
        report["service_identity"]=fields
    except (OSError,subprocess.TimeoutExpired):
        report["service_query"]="UNAVAILABLE"
    return report

if __name__=="__main__":
    print(json.dumps(inspect(),indent=2))
