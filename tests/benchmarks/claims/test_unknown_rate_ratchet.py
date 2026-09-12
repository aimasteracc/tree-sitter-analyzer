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

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

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


def _measure_unknown_rate() -> tuple[float, int, int]:
    """Measure the unknown callee-resolution rate over this repository.

    Scoped to the product source (`tree_sitter_analyzer/`): the claim is about
    the resolver's behaviour on real code, this is real code, and it keeps the
    build around six seconds on the axis that can afford it. `workers=1` is
    deliberate — the default pool spawns processes, and a measured number must
    not depend on pool scheduling.
    """
    from tree_sitter_analyzer.ast_cache import ASTCache

    source_root = PROJECT_ROOT / "tree_sitter_analyzer"
    cache = ASTCache(str(source_root))
    try:
        cache.index_project(workers=1)
        row = (
            cache.get_conn()
            .execute(
                "SELECT COUNT(*), SUM(callee_resolution = 'unknown') "
                "FROM edges WHERE kind = 'calls'"
            )
            .fetchone()
        )
    finally:
        cache.close()
    total, unknown = int(row[0]), int(row[1] or 0)
    if total <= 0:
        # A precondition of the measurement, not an assertion about the
        # repository.  An exact edge count would be worse than the bound it
        # replaced: this test is a strict xfail, so a corpus change would move
        # the count, the test would xfail for the wrong reason, and a genuine
        # crossing of UNKNOWN_RATE_THRESHOLD_PCT would go unnoticed underneath.
        raise RuntimeError(
            "no CALLS edges were indexed, so the rate below would divide "
            "nothing; the measurement is broken, not the resolver"
        )
    return 100.0 * unknown / total, unknown, total


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Measured 2026-09-12: 9.78% on the product source (4,941 / 50,528 CALLS "
        "edges) and 6.27% on a 2,174-file self-repo subset, against a 6.0% "
        "ceiling. The claim is not met, and it was not met while two tests "
        "asserted the ceiling constant and that this file contains its own text. "
        "Strict rather than skipped: the xfail is removed when the resolver "
        "improves, and raising UNKNOWN_RATE_THRESHOLD_PCT to silence it turns "
        "this into an unexpected pass and fails the run — which is the 'never "
        "increase without a reviewed decision' rule enforced for the first time."
    ),
)
def test_unknown_rate_is_measured_within_threshold():
    """The claim, measured instead of restated (RFC-0028 §3.2).

    Replaces two tests that could not fail: `test_unknown_rate_threshold_value`
    asserted `UNKNOWN_RATE_THRESHOLD_PCT == 6.0` (a constant equalling itself)
    and `test_unknown_rate_threshold_is_documented_in_this_file` asserted that
    this file contains the string "6.0". Neither observed the code, so neither
    noticed the rate had drifted above the ceiling they pin. §3.2 asks whether a
    gate actually gates.
    """
    measured, unknown, total = _measure_unknown_rate()
    print(
        f"[claim] unknown_rate measured={measured:.2f}% unknown={unknown} "
        f"total={total} threshold={UNKNOWN_RATE_THRESHOLD_PCT}%"
    )
    assert measured <= UNKNOWN_RATE_THRESHOLD_PCT, (
        f"unknown rate {measured:.2f}% exceeds the {UNKNOWN_RATE_THRESHOLD_PCT}% "
        f"ceiling ({unknown}/{total} CALLS edges unresolved)"
    )
