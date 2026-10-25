
"""Research-only unified diagnostic freshness classification."""

from research.diagnostic_freshness_prototype.component_cycle_tracker import classify_cycle_components


def classify_freshness(current_cycle_id, evidence):
    components = classify_cycle_components(
        current_cycle_id, evidence
    )

    statuses = set(components.values())

    if "UNKNOWN" in statuses:
        overall = "UNKNOWN"
    elif statuses == {"RECALCULATED"}:
        overall = "CURRENT"
    elif statuses == {"NOT_RECALCULATED"}:
        overall = "STALE"
    else:
        overall = "PARTIAL"

    return {
        "diagnostics_freshness": overall,
        "component_freshness": components,
        "diagnostics_cycle_verified": overall != "UNKNOWN",
    }
