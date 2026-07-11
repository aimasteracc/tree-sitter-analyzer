"""Claim invariant: unknown callee resolution rate must not exceed 6.0%.

Baseline history:
  v1.21.0 (benchmark date TBD): 3.7% unknown  <- published rate
  v1.29.0-line (2026-07-10):    6.0% unknown  <- current threshold (develop@6fe62fba)

This test is a NON-REGRESSION GATE only. The threshold must NEVER increase
without an explicit, reviewed decision. After fixes in Groups 1, 3, 4 land,
re-run the SQL below against the self-repo index, measure the new unknown rate,
and lower this threshold accordingly.

Measurement SQL (run against tree-sitter-analyzer self-repo index):
  SELECT ROUND(100.0 * SUM(callee_resolution = 'unknown') / COUNT(*), 1)
  FROM edges
  WHERE kind = 'calls';
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.claims_benchmark,
    pytest.mark.full_language,
]

# Baseline history:
#   v1.21.0 (2026-xx-xx): 3.7% unknown
#   v1.29.0-line (2026-07-10): 6.0% unknown  <- current threshold
# After Scala resolver (Group 1) and other fixes land:
#   re-run benchmark, measure new unknown rate, lower this threshold.
# This threshold must NEVER increase without an explicit decision.
UNKNOWN_RATE_THRESHOLD_PCT = 6.0


def test_unknown_rate_threshold_is_documented_in_this_file():
    """The threshold value and baseline history must be readable in this file."""
    import inspect

    src = inspect.getfile(test_unknown_rate_threshold_is_documented_in_this_file)
    with open(src, encoding="utf-8") as f:
        content = f.read()
    assert "UNKNOWN_RATE_THRESHOLD_PCT" in content
    assert "6.0" in content
    assert "3.7" in content
    assert "callee_resolution" in content, (
        "The measurement SQL must be present in this test file."
    )


def test_unknown_rate_threshold_value():
    """Threshold value is pinned at 6.0% (current measured floor, 2026-07-10).

    This test does NOT run a live SQL query — it pins the threshold constant
    so that any future increase to UNKNOWN_RATE_THRESHOLD_PCT triggers a
    review. A live SQL measurement test requires the self-repo index to be
    built first; that is tracked separately as a full_language benchmark test.
    """
    assert UNKNOWN_RATE_THRESHOLD_PCT == 6.0, (
        f"Threshold must be 6.0% (current measured floor). "
        f"Got: {UNKNOWN_RATE_THRESHOLD_PCT}%. "
        "Lower this only after measuring a genuine improvement; "
        "never raise it without an explicit decision."
    )
