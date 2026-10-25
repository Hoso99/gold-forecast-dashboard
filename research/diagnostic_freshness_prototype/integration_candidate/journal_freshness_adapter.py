"""Isolated research-only journal freshness adapter."""

COMPONENTS = (
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
)


def unknown_freshness():
    return {
        "diagnostics_freshness": "UNKNOWN",
        "component_freshness": {
            name: "UNKNOWN" for name in COMPONENTS
        },
        "diagnostics_cycle_verified": False,
    }


def journal_freshness(evidence):
    """Return observational metadata without affecting decisions."""
    if evidence is None:
        return unknown_freshness()

    try:
        from unified_freshness import classify_freshness

        cycle_id = evidence.cycle_id
        snapshot = evidence.snapshot()

        result = classify_freshness(cycle_id, snapshot)

        if not isinstance(result, dict):
            return unknown_freshness()

        if result.get("diagnostics_freshness") not in (
            "CURRENT", "PARTIAL", "STALE", "UNKNOWN"
        ):
            return unknown_freshness()

        components = result.get("component_freshness")

        if not isinstance(components, dict):
            return unknown_freshness()

        if set(components) != set(COMPONENTS):
            return unknown_freshness()

        if any(
            value not in (
                "RECALCULATED",
                "NOT_RECALCULATED",
                "UNAVAILABLE",
                "UNKNOWN",
            )
            for value in components.values()
        ):
            return unknown_freshness()

        return result

    except Exception:
        return unknown_freshness()
