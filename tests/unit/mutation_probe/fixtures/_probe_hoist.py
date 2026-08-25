"""Probe test: hoist target (RFC-0029 item 1).

This file is intentionally NOT named test_*.py so it is not auto-discovered.
The mutation probe invokes it explicitly by full node id.
"""

from tests.unit.mutation_probe.fixtures.hoist_target import compute


def test_compute_returns_42() -> None:
    # Exact assertion: compute() must return exactly 42.
    # After a hoist mutation the return value is still 42, so this test does
    # NOT constrain the code — that is the expected probe outcome.
    assert compute() == 42
