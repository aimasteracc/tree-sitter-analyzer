"""Probe test: boolean/comparison target (RFC-0029 items 3 & 4).

Three independent tests, each checking exactly one observable fact.
"""

from tests.unit.mutation_probe.fixtures.bool_target import divide, is_positive


def test_is_positive_true() -> None:
    assert is_positive(5) is True


def test_is_positive_false() -> None:
    assert is_positive(-1) is False


def test_divide_basic() -> None:
    assert divide(10, 2) == 5.0
