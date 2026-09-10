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

2026-07-10 re-measurement note: re-running the same pinned SQL against current
develop (commit 6fe62fba, TSA v1.29.0-line) gives **94.0%** (140,776 `calls`
edges; `unknown` grew from ~3.7% to ~6.0% as the codebase and its edge-extraction
surface grew over 13 releases). The 96.3% figure asserted below is deliberately
NOT changed to 94.0% — REPORT-v1.21.0.md is a dated, versioned snapshot report
and 96.3% is what was genuinely measured at v1.21.0; rewriting it would misrepresent
that historical measurement. The live 94.0% figure is recorded as its own
inline "Measurement note" in REPORT-v1.21.0.md (Headline correctness numbers
section) and pinned separately by
``test_v1_29_0_reverification_note_is_present_in_report`` below, so both the
historical claim and the current live number stay independently verifiable.
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


def test_v1_29_0_reverification_note_is_present_in_report():
    """The 2026-07-10 TSA-only re-measurement note must remain in the report.

    Guards the annotation added alongside the pinned v1.21.0 96.3% figure: the
    historical claim is intentionally left unchanged (see module docstring),
    but the live re-measurement (94.0%, current develop) must stay documented
    next to it so the report does not silently drift back to looking like a
    single, un-annotated, unverified snapshot.
    """
    content = REPORT.read_text(encoding="utf-8")
    assert "94.0%" in content, (
        "REPORT-v1.21.0.md must retain the 2026-07-10 re-measured 94.0% "
        "classification-rate figure (develop@6fe62fba)."
    )
    assert "Measurement note (2026-07-10" in content, (
        "REPORT-v1.21.0.md must retain the 2026-07-10 re-measurement note "
        "documenting the TSA-only refresh (classification rate + "
        "cross-language edge count) against current develop."
    )
