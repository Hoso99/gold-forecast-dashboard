
"""Isolated research-only component freshness tracker."""

COMPONENTS = (
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
)


def classify_cycle_components(current_cycle_id, evidence):
    result = {name: "UNKNOWN" for name in COMPONENTS}

    if not isinstance(current_cycle_id, str) or not current_cycle_id:
        return result

    if not isinstance(evidence, dict):
        return result

    if evidence.get("cycle_id") != current_cycle_id:
        return result

    attempted = evidence.get("attempted")
    unavailable = evidence.get("unavailable", ())

    if not isinstance(attempted, (list, tuple, set)):
        return result

    if not isinstance(unavailable, (list, tuple, set)):
        return result

    if any(name not in COMPONENTS for name in attempted):
        return result

    if any(name not in COMPONENTS for name in unavailable):
        return result

    if not set(unavailable).issubset(set(attempted)):
        return result

    for name in COMPONENTS:
        if name in unavailable:
            result[name] = "UNAVAILABLE"
        elif name in attempted:
            result[name] = "RECALCULATED"
        else:
            result[name] = "NOT_RECALCULATED"

    return result
