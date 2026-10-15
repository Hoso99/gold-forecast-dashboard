"""Read-only audit of available V9.5 paper trade evidence on Oracle.

Reports counts and schema keys only, never position values or credentials.
"""
import json
import os
from pathlib import Path

def audit():
    root = Path("/home/ubuntu/.local/state/v95-research")
    paths = {
        "trade_history":root/"trade_history.jsonl",
        "decision_journal":root/"decisions.jsonl",
        "state":root/"state.json",
    }
    report={}
    for name,path in paths.items():
        item={"exists":path.is_file(),"readable":os.access(path,os.R_OK),"records":None,"field_names":[]}
        if item["exists"] and item["readable"]:
            try:
                if path.suffix==".jsonl":
                    count=0
                    fields=set()
                    with path.open(encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                obj=json.loads(line)
                                if isinstance(obj,dict):fields.update(obj)
                                count+=1
                    item["records"]=count
                    item["field_names"]=sorted(fields)
                else:
                    with path.open(encoding="utf-8") as f: obj=json.load(f)
                    if isinstance(obj,dict):item["field_names"]=sorted(obj)
            except (OSError, ValueError, json.JSONDecodeError):
                item["inspection"]="UNAVAILABLE"
        report[name]=item
    return report

if __name__=="__main__":
    print(json.dumps(audit(),indent=2))
