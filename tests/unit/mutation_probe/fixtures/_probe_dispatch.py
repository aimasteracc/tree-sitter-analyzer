"""Probe test: dispatch target (RFC-0029 item 2).

Two tests: one exercises _private() directly, one goes through public_dispatch().
"""

from tests.unit.mutation_probe.fixtures.dispatch_target import _private, public_dispatch


def test_private_returns_double() -> None:
    # Calls _private() directly; does NOT exercise public_dispatch().
    assert _private(5) == 10


def test_dispatch_positive() -> None:
    # Goes through public_dispatch() which delegates to _private().
    assert public_dispatch(5) == 10
