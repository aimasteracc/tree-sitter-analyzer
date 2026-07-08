"""Claim invariant: 96.3% call edge classification rate.

README claim (benchmarks/codegraph_compare/REPORT-v1.21.0.md):
    "Edge classification rate: 96.3% of call edges resolve to a non-'unknown'
    callee_resolution."

The exact SQL pinned in the report:
    SELECT ROUND(100.0*SUM(callee_resolution!='unknown')/COUNT(*),1)
    FROM edges WHERE kind='calls';

This invariant:
    1. Pins the published 96.3% classification rate in the benchmark report.
    2. Documents the measurement SQL so it can be re-run later.
    3. Marks the "96.3% on this repo" check as full_language + claims_benchmark
       because the claim belongs to the full repo benchmark, not the PR smoke set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.claims_benchmark,
    pytest.mark.full_language,
]

ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "benchmarks" / "codegraph_compare" / "REPORT-v1.21.0.md"


def test_call_edge_classification_rate_is_pinned_in_report():
    """The published report must pin the 96.3% classification claim exactly."""
    content = REPORT.read_text(encoding="utf-8")
    assert "Edge classification rate: 96.3%" in content, (
        "REPORT-v1.21.0.md must pin the published 96.3% classification rate."
    )
    assert (
        "SELECT ROUND(100.0*SUM(callee_resolution!='unknown')/COUNT(*),1)" in content
    ), "The measurement SQL for the 96.3% claim must remain in the report."


def test_classification_rate_sql_is_documented():
    """The measurement SQL must be present in this file (docs-as-tests pattern).

    Ensures that when someone wants to re-run the 96.3% claim, they can find
    the command in the test that guards the claim.
    """
    import inspect

    src = inspect.getfile(test_classification_rate_sql_is_documented)
    with open(src, encoding="utf-8") as f:
        content = f.read()
    assert "callee_resolution" in content, (
        "The measurement SQL for the 96.3% classification claim must be "
        "present in this test file for repro visibility."
    )
    assert "96.3" in content, (
        "The README claim value '96.3%' must be referenced in this test file."
    )
