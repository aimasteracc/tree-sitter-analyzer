"""The unit-test time budget: CPU-bound regressions fail, runner contention does not."""

from __future__ import annotations

import pytest

from scripts.classify_windows_pytest_failure import classify
from tests.unit_time_budget import (
    BUDGET_FAILURE_PREFIX,
    UnitTimeBudget,
    budget_for,
    budget_violation,
    excused_summary_lines,
    is_excused,
)


@pytest.mark.parametrize(
    ("platform", "on_ci", "expected"),
    [
        ("linux", False, UnitTimeBudget(5.0, 5.0)),
        ("win32", False, UnitTimeBudget(8.0, 8.0)),
        ("darwin", True, UnitTimeBudget(8.0, 16.0)),
        ("win32", True, UnitTimeBudget(12.8, 25.6)),
    ],
)
def test_budget_scales_once_for_ci_runners(platform, on_ci, expected) -> None:
    got = budget_for(platform, on_ci=on_ci)
    assert (round(got.limit_s, 6), round(got.wall_ceiling_s, 6)) == (
        expected.limit_s,
        expected.wall_ceiling_s,
    )


def test_local_runs_keep_the_strict_wall_clock_limit() -> None:
    # 本地 ceiling == limit：墙钟超限即失败，与 CPU 时间无关（与改动前一致）。
    budget = budget_for("linux", on_ci=False)
    assert budget_violation(budget, wall_s=5.1, cpu_s=0.1) is not None
    assert budget_violation(budget, wall_s=4.9, cpu_s=4.9) is None


def test_contended_runner_wall_time_alone_does_not_fail() -> None:
    # CI 2026-10-24：全量索引测试墙钟 13-17 s，而测试本身的 CPU 远低于预算。
    budget = budget_for("win32", on_ci=True)
    assert budget_violation(budget, wall_s=17.14, cpu_s=6.0) is None


def test_cpu_bound_regression_still_fails_on_ci() -> None:
    budget = budget_for("win32", on_ci=True)
    message = budget_violation(budget, wall_s=14.0, cpu_s=13.5)
    assert message is not None
    assert message.startswith(f"{BUDGET_FAILURE_PREFIX} 14.00s > 12.8s; process CPU")


def test_wall_ceiling_catches_unmocked_waits_on_ci() -> None:
    budget = budget_for("darwin", on_ci=True)
    message = budget_violation(budget, wall_s=16.5, cpu_s=0.2)
    assert message is not None
    assert "16.0s ceiling" in message


def test_multithreaded_cpu_inside_the_wall_limit_is_not_a_violation() -> None:
    # 多线程测试 CPU 可以超过墙钟；墙钟未超限时不应比改动前更严格。
    budget = budget_for("linux", on_ci=True)
    assert budget_violation(budget, wall_s=3.0, cpu_s=11.0) is None


def test_budget_failures_stay_retry_eligible_for_the_ci_classifier() -> None:
    message = budget_violation(budget_for("win32", on_ci=True), wall_s=30.0, cpu_s=1.0)
    assert message is not None
    first_line = message.splitlines()[0]
    output = f"FAILED tests/unit/test_x.py::test_y - Failed: {first_line}\n"
    assert classify(output)["retry_eligible"] is True


def test_excused_overruns_are_reported_not_hidden() -> None:
    budget = budget_for("win32", on_ci=True)
    assert is_excused(budget, wall_s=17.14, cpu_s=6.0) is True
    assert is_excused(budget, wall_s=10.0, cpu_s=1.0) is False  # inside the limit
    assert is_excused(budget, wall_s=14.0, cpu_s=13.5) is False  # a violation
    lines = excused_summary_lines(
        budget, [("t::fast", 13.0, 2.0), ("t::slow", 17.14, 6.0)]
    )
    assert lines[0].startswith("2 unit test(s) were over the 12.8s limit")
    assert [line.split()[-1] for line in lines[1:]] == ["t::slow", "t::fast"]
