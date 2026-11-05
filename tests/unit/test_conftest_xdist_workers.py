"""``-n auto`` sizing in tests/conftest.py honours PYTEST_XDIST_AUTO_NUM_WORKERS."""

from __future__ import annotations

import pytest

from tests import conftest


@pytest.mark.parametrize(("value", "expected"), [("4", 4), (" 2 ", 2), ("0", 1)])
def test_configured_worker_count_wins_over_the_cpu_count(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", value)
    monkeypatch.setattr(conftest.os, "cpu_count", lambda: 3)
    monkeypatch.setattr(conftest.sys, "platform", "darwin")
    assert conftest.pytest_xdist_auto_num_workers(None) == expected


@pytest.mark.parametrize(("platform", "expected"), [("darwin", 3), ("win32", 4)])
def test_unset_variable_keeps_the_platform_default(
    monkeypatch: pytest.MonkeyPatch, platform: str, expected: int
) -> None:
    monkeypatch.delenv("PYTEST_XDIST_AUTO_NUM_WORKERS", raising=False)
    monkeypatch.setattr(conftest.os, "cpu_count", lambda: 3)
    monkeypatch.setattr(conftest.sys, "platform", platform)
    assert conftest.pytest_xdist_auto_num_workers(None) == expected


def test_non_integer_value_is_a_usage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYTEST_XDIST_AUTO_NUM_WORKERS", "auto")
    with pytest.raises(pytest.UsageError, match="'auto'"):
        conftest.pytest_xdist_auto_num_workers(None)
