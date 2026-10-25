
"""Research-only diagnostic evaluation evidence."""

from uuid import uuid4

COMPONENTS = (
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
)


class FreshnessEvidence:
    def __init__(self):
        self.cycle_id = uuid4().hex
        self.completed = set()
        self.unavailable = set()

    def mark_completed(self, component):
        if component not in COMPONENTS:
            raise ValueError("Unknown diagnostic component")
        self.completed.add(component)
        self.unavailable.discard(component)

    def mark_unavailable(self, component):
        if component not in COMPONENTS:
            raise ValueError("Unknown diagnostic component")
        self.unavailable.add(component)
        self.completed.discard(component)

    def snapshot(self):
        attempted = self.completed | self.unavailable
        return {
            "cycle_id": self.cycle_id,
            "attempted": sorted(attempted),
            "unavailable": sorted(self.unavailable),
        }
