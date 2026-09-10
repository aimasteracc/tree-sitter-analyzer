"""Probe test: relative-import target (RFC-0029 item 8).

After mutation of rel_import_target.py, the relative import ``from . import
rel_import_helper`` must survive (no ImportError).  If it did, the test would
fail with NON_ASSERTION, not ASSERTION — the probe would then emit
MUTATED_RUN_CRASHED instead of ``constrains``.
"""

from tests.unit.mutation_probe.fixtures.rel_import_target import compute


def test_compute_rel_import() -> None:
    assert compute(2) == 42
