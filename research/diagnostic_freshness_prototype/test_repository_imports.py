"""Verify freshness imports without the isolated test runner's extra paths."""

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class RepositoryImportTests(unittest.TestCase):

    def test_repository_qualified_freshness_imports(self):
        script = """
from research.diagnostic_freshness_prototype.integration_candidate.freshness_evidence import FreshnessEvidence
from research.diagnostic_freshness_prototype.integration_candidate.journal_freshness_adapter import journal_freshness
from research.diagnostic_freshness_prototype.unified_freshness import classify_freshness

evidence = FreshnessEvidence()
evidence.mark_completed("diagnostics")
result = journal_freshness(evidence)

assert result["diagnostics_freshness"] == "PARTIAL"
assert result["component_freshness"]["diagnostics"] == "RECALCULATED"
assert result["diagnostics_cycle_verified"] is True
"""

        env = {
            "HOME": os.environ["HOME"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(REPO),
        }

        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )
