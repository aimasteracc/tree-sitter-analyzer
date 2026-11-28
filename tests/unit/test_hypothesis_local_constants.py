"""Guard: Hypothesis must not harvest constants from every loaded module."""

from __future__ import annotations

from hypothesis.internal.conjecture import providers

from tests.hypothesis_local_constants import disable_local_constants


def test_local_constant_scan_is_disabled_by_conftest() -> None:
    constants = providers._get_local_constants()
    assert len(constants) == 0


def test_disable_local_constants_is_idempotent() -> None:
    assert disable_local_constants() is True
    assert len(providers._get_local_constants()) == 0
