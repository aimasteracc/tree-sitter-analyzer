"""Per-test runtime budget for unit tests: the single place it is computed.

History (see ``tests/conftest.py``): two real regressions -- per-call
``source.encode()`` in a node-text helper, and tests that silently built the
DependencyGraph of the whole repository -- each showed up as one unit test
crossing a few seconds. The budget fails such a test so the cost is fixed or
documented with ``@pytest.mark.slow_ok``.

Both regressions burn CPU *in the test process*. Wall time on a shared CI
runner also counts time the test spent waiting for a core or for the disk:
with four xdist workers on a four-vCPU Windows runner, full-index tests that
take 3-5 s locally were observed at 13-17 s wall (CI runs 40095395832 and
40095406288, 2026-10-24) while doing no extra work. Failing those is noise,
and once the global ``--reruns`` was removed (#1806) it turned develop red.

So the budget is judged on two clocks:

* ``limit_s`` -- a test fails when it is over the limit on wall time *and* on
  process CPU time (``time.process_time``: every thread of this process).
  CPU time does not grow while the runner is contended, so the CPU-bound
  regressions above still fail, on every runner.
* ``wall_ceiling_s`` -- a hard wall-time cap that fails regardless of CPU time,
  for costs that do not burn CPU here (real ``sleep``, unmocked subprocesses).
  Locally the ceiling equals the limit, so local runs are exactly as strict
  as before. On CI the ceiling is ``CI_WALL_CEILING_FACTOR`` times the limit.

The ``Unit test exceeded per-test budget:`` prefix of the failure message is
parsed by ``scripts/classify_windows_pytest_failure.py``; keep it.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Base limit per platform (Windows process start-up and file I/O are slower).
BASE_LIMIT_S = {"win32": 8.0}
DEFAULT_BASE_LIMIT_S = 5.0
#: CI runners are shared; wall-clock variance there is about 1.6x (#1364).
CI_LIMIT_FACTOR = 1.6
#: On CI, wall time may exceed the limit by this factor when the test's own
#: CPU time stays inside the limit (the runner was contended, not the test).
CI_WALL_CEILING_FACTOR = 2.0

BUDGET_FAILURE_PREFIX = "Unit test exceeded per-test budget:"


@dataclass(frozen=True)
class UnitTimeBudget:
    limit_s: float
    wall_ceiling_s: float


def budget_for(platform: str, *, on_ci: bool) -> UnitTimeBudget:
    """Return the budget for ``platform`` (a ``sys.platform`` value)."""
    limit = BASE_LIMIT_S.get(platform, DEFAULT_BASE_LIMIT_S)
    if not on_ci:
        return UnitTimeBudget(limit_s=limit, wall_ceiling_s=limit)
    limit *= CI_LIMIT_FACTOR
    return UnitTimeBudget(limit_s=limit, wall_ceiling_s=limit * CI_WALL_CEILING_FACTOR)


#: ``user_properties`` key for a test whose wall time was over the limit but
#: was excused because its CPU time was not (reported in the terminal summary,
#: so the allowance is never silent).
EXCUSED_PROPERTY = "unit_time_budget_excused"


def is_excused(budget: UnitTimeBudget, *, wall_s: float, cpu_s: float) -> bool:
    """Over the limit on wall time only, and inside the ceiling."""
    return (
        wall_s > budget.limit_s
        and budget_violation(budget, wall_s=wall_s, cpu_s=cpu_s) is None
    )


def excused_summary_lines(
    budget: UnitTimeBudget, excused: list[tuple[str, float, float]]
) -> list[str]:
    """Terminal-summary lines, slowest first, for ``(nodeid, wall, cpu)`` rows."""
    lines = [
        f"{len(excused)} unit test(s) were over the {budget.limit_s:.1f}s limit on "
        f"wall time but not on process CPU time (ceiling "
        f"{budget.wall_ceiling_s:.1f}s); see tests/unit_time_budget.py:"
    ]
    for nodeid, wall, cpu in sorted(excused, key=lambda row: -row[1]):
        lines.append(f"  {wall:6.2f}s wall {cpu:6.2f}s cpu  {nodeid}")
    return lines


def budget_violation(
    budget: UnitTimeBudget, *, wall_s: float, cpu_s: float
) -> str | None:
    """Return the failure message when the test is over budget, else ``None``."""
    over_ceiling = wall_s > budget.wall_ceiling_s
    over_limit = wall_s > budget.limit_s and cpu_s > budget.limit_s
    if not (over_ceiling or over_limit):
        return None
    if over_limit:
        clock = f"process CPU {cpu_s:.2f}s is also over the limit"
    else:
        clock = (
            f"wall time is over the {budget.wall_ceiling_s:.1f}s ceiling "
            f"(process CPU {cpu_s:.2f}s)"
        )
    return (
        f"{BUDGET_FAILURE_PREFIX} {wall_s:.2f}s > {budget.limit_s:.1f}s; {clock}.\n"
        "Common causes (see tests/unit_time_budget.py and tests/conftest.py):\n"
        "  - Accidentally scanning the whole repo "
        "(project_root='/tmp' or =None when cwd is the repo)\n"
        "  - Per-call O(file_size) work in a tight loop "
        "(e.g. source.encode() inside a node-text helper)\n"
        "  - Real subprocess / network / sleep without a mock\n"
        "Fix the perf, or -- if the cost is real and documented -- add "
        "@pytest.mark.slow_ok with a justifying comment."
    )
