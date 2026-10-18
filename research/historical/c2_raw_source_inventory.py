"""Research-only inventory of C2 Raw episode sources. No file contents or secrets."""
import json
from pathlib import Path

ROOTS = [
    Path("/home/ubuntu/v95-private-export/research"),
    Path("/home/ubuntu/v95-detector-dev/research"),
    Path("/home/ubuntu/v95-historical-research"),
]
KEYS = ("c2", "reversal", "reject", "episode")
EXTENSIONS = {".json", ".jsonl", ".csv", ".py", ".md"}
matches = []
for root in ROOTS:
    if not root.is_dir():
        continue
    for p in root.rglob("*"):
        if not p.is_file() or p.is_symlink() or p.suffix.lower() not in EXTENSIONS:
            continue
        if not any(k in p.name.lower() for k in KEYS):
            continue
        # Inventory metadata only, never contents, tokens or credentials.
        st = p.stat()
        matches.append({"path": str(p), "bytes": st.st_size})
report = {"research_only": True, "files": sorted(matches, key=lambda x:x["path"]),
          "note": "Metadata inventory only; no episode classifications or changes."}
Path("c2-raw-source-inventory.json").write_text(json.dumps(report, indent=2)+"\n")
print("C2_RAW_SOURCE_FILES", len(matches))
print("C2_RAW_SOURCE_INVENTORY_COMPLETE")
