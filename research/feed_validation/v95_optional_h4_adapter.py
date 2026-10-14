"""Research-only adapter for optional H4 diagnostics.

Does not alter the executable V9.5 SELL detectors, paper state, or order logic.
Import only after the existing monitor has been reviewed and backed up.
"""
from v95_indicators import diagnostics
from v95_research_votes import votes


def evaluate_optional_h4(m1, m5, m15, h1, h4):
    """Return existing diagnostics and research votes without fabricating H4.

    Research trend votes that require H4 are explicitly unavailable, not false.
    Existing research-vote arithmetic is left untouched whenever H4 is valid.
    """
    info = diagnostics(m1, m5, m15, h1, h4)
    if len(h4) >= 2:
        return info, votes(m1, m5, m15, h1, h4)
    info["h4_bearish"] = None
    # Calculate non-H4 research votes through the original function with
    # an empty H4? That function refuses all votes, so do not invent substitutes.
    return info, {
        "status": "H4_UNAVAILABLE",
        "votes": {},
        "trend_vote": "UNAVAILABLE",
        "reason": "H4-dependent research votes skipped; core SELL logic unaffected",
        "independence_verified": False,
    }
