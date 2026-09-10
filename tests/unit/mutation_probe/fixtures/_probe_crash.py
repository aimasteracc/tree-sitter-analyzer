"""Probe test: crash target (RFC-0029 item 4).

After a hoist mutation, get_bound() raises NameError — a non-assertion crash.
"""

from tests.unit.mutation_probe.fixtures.crash_target import get_bound


def test_get_bound_is_str() -> None:
    assert isinstance(get_bound(), str)
