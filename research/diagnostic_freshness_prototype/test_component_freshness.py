
import unittest


COMPONENTS = (
    "diagnostics",
    "research_votes",
    "shadow_entry",
    "core_sell_detectors",
)


def classify_components(attempted, unavailable=()):
    """Research-only component freshness contract."""
    attempted = set(attempted)
    unavailable = set(unavailable)

    result = {}

    for component in COMPONENTS:
        if component in unavailable and component in attempted:
            result[component] = "UNAVAILABLE"
        elif component in attempted:
            result[component] = "RECALCULATED"
        else:
            result[component] = "NOT_RECALCULATED"

    return result


class ComponentFreshnessTests(unittest.TestCase):

    def test_before_diagnostics(self):
        result = classify_components(())
        self.assertTrue(
            all(v == "NOT_RECALCULATED" for v in result.values())
        )

    def test_existing_position_partial_evaluation(self):
        result = classify_components((
            "diagnostics",
            "research_votes",
            "shadow_entry",
        ))
        self.assertEqual(
            result["core_sell_detectors"],
            "NOT_RECALCULATED",
        )

    def test_full_sell_evaluation(self):
        result = classify_components(COMPONENTS)
        self.assertTrue(
            all(v == "RECALCULATED" for v in result.values())
        )

    def test_optional_h4_unavailable(self):
        result = classify_components(
            COMPONENTS,
            unavailable=("diagnostics", "research_votes"),
        )
        self.assertEqual(
            result["diagnostics"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            result["research_votes"],
            "UNAVAILABLE",
        )
        self.assertEqual(
            result["core_sell_detectors"],
            "RECALCULATED",
        )

    def test_unattempted_cannot_be_unavailable(self):
        result = classify_components(
            (),
            unavailable=("diagnostics",),
        )
        self.assertEqual(
            result["diagnostics"],
            "NOT_RECALCULATED",
        )


if __name__ == "__main__":
    unittest.main()
