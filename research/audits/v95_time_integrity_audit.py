"""V9.5 offline audit of H1/H4 candle completion and potential leakage.

Print structural source excerpts and dataset timing coverage for human review.
No orders, market calls, or production file writes.
"""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[2]
for name in ("candle_dynamics_v94.py", "sr_location_research_v94.py", "compare_candle_windows_v94.py", "candle_power_v94.py"):
    path = root / name
    if not path.exists():
        print("NOT_FOUND", name)
        continue
    source = path.read_text(encoding="utf-8")
    print("SOURCE", name, "bytes", len(source))
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        print("SYNTAX_ERROR", exc)
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
            word in node.name.lower() for word in ("context", "resample", "feature", "align", "h4", "h1")
        ):
            print("FUNCTION", node.name, "line", node.lineno)
    for lineno, line in enumerate(source.splitlines(), 1):
        if any(word in line.lower() for word in ("shift(", "resample(", "merge_asof", "h4_end", "h1_end", "lookahead", "forward_")):
            print("TIMING_LINE", name, lineno, line.strip()[:180])
print("NOTE: source inspection is not sufficient to prove absence of lookahead bias.")
