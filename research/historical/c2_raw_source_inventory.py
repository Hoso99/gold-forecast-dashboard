"""Research-only metadata inventory of C2 Raw sources; no file contents or secrets."""
import json
import os
from pathlib import Path

ROOTS = [
    Path("/home/ubuntu/v95-private-export/research"),
    Path("/home/ubuntu/v95-detector-dev/research"),
    Path("/home/ubuntu/v95-historical-research"),
    Path("/home/v95research"),
]
KEYS = ("c2", "reversal", "reject", "episode")
EXTENSIONS = {".json", ".jsonl", ".csv", ".py", ".md"}
matches = []
roots = []
errors = []

def error(reason, path):
    errors.append({"reason": reason, "path": str(path)})

def walk_error(e):
    error("permission_denied" if isinstance(e, PermissionError) else "unreadable", e.filename or "(unknown)")

for root in ROOTS:
    try:
        is_dir = root.is_dir()
    except PermissionError:
        roots.append({"root": str(root), "status": "permission_denied"})
        continue
    if not is_dir:
        roots.append({"root": str(root), "status": "not_a_directory_or_missing"})
        continue
    roots.append({"root": str(root), "status": "scanned"})
    for current, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", "actions-runner")]
        for filename in files:
            if not any(k in filename.lower() for k in KEYS):
                continue
            p = Path(current) / filename
            if p.suffix.lower() not in EXTENSIONS:
                continue
            try:
                if not p.is_symlink() and p.is_file():
                    matches.append({"path": str(p), "bytes": p.stat().st_size})
            except (OSError, PermissionError):
                error("unreadable_file", p)

report = {
    "research_only": True, "files": sorted(matches, key=lambda x: x["path"]),
    "roots": roots, "scan_errors": errors[:100],
    "note": "Metadata inventory only; inaccessible directories skipped; no permission changes.",
}
Path("c2-raw-source-inventory.json").write_text(json.dumps(report, indent=2) + "\n")
print("C2_RAW_SOURCE_FILES", len(matches))
print("C2_RAW_INACCESSIBLE_ROOTS", sum(x["status"] == "permission_denied" for x in roots))
print("C2_RAW_SOURCE_INVENTORY_COMPLETE")
