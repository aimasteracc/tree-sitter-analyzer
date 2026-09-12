#!/usr/bin/env python3
"""RFC-0028 §3.2 — every workflow gate names its marker set and its job.

§3.2 asks each gate to name the marker set it runs under and the CI job that runs
it, and to prove the set is not empty. An empty set is the failure mode: a job
invoked as `pytest -m "<marker>"` that no test carries collects zero tests and
reports success, which is a gate that cannot gate.

**How the proof is made, and its limit.** Running `pytest --collect-only` costs
5–15 s per expression on this tree, so five expressions would add roughly a
minute to the fast suite — a gate that makes the default loop slower is a gate
people disable. This checks statically instead: every marker name must be
registered, and every *positive* marker in the expression must be carried by at
least one test file. That catches the vacuity case (a marker nothing carries) and
the typo case, without the subprocess cost. It does **not** read a collected
count, so §3.2's item stays open on that point.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
PYTEST_INI = PROJECT_ROOT / "pytest.ini"
TESTS_DIR = PROJECT_ROOT / "tests"

_MARKER_FLAG = re.compile(r"-m\s+[\"']([^\"']+)[\"']")
_MARKER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_KEYWORDS = frozenset({"and", "or", "not"})
_SUBSTITUTION = re.compile(r"\$\{[^}]*\}")


def _resolvable(expression: str) -> str:
    """The expression with shell substitutions removed.

    `-m "e2e${EXTRA_MARKS}"` is a runtime value the workflow composes; tokenizing
    it literally would report `EXTRA_MARKS` as an unregistered marker, which is
    about the shell, not the gate.
    """
    return _SUBSTITUTION.sub("", expression)


_PYTEST_INVOCATION = re.compile(r"\bpytest\s")


def _pytest_marker_expressions(command: str) -> list[str]:
    """Marker expressions from pytest invocations in one ``run`` block.

    Continuation-aware, because these invocations wrap across lines with a
    trailing backslash and the `-m` sits on the last of them. And `-m` is only a
    marker flag on a logical line that *invokes* pytest: `git commit -m "..."` and
    `gh ... -m "..."` take a message, and matching those yields 23 phantom gates.
    """
    logical_lines: list[str] = []
    buffer = ""
    for raw in command.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            buffer += line[:-1] + " "
            continue
        buffer += line
        logical_lines.append(buffer)
        buffer = ""
    if buffer:
        logical_lines.append(buffer)

    expressions: list[str] = []
    for logical in logical_lines:
        if _PYTEST_INVOCATION.search(logical):
            expressions.extend(_MARKER_FLAG.findall(logical))
    return expressions


def _workflow_marker_sets() -> list[tuple[str, str, str]]:
    """``(workflow, job_key, marker_expression)`` for every gate that runs tests.

    Expressions containing a shell substitution are returned but cannot be
    resolved statically; the caller asserts they are exactly the known templated
    ones, so a new one is a decision rather than a silent skip.
    """
    found: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_key, job in (document.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if not isinstance(step, dict):
                    continue
                command = step.get("run")
                if not isinstance(command, str):
                    continue
                for expression in _pytest_marker_expressions(command):
                    found.append((path.name, str(job_key), expression))
    return found


def _registered_markers() -> set[str]:
    """Markers from ``pytest.ini`` plus any registered through a conftest."""
    registered = set()
    in_markers = False
    for line in PYTEST_INI.read_text(encoding="utf-8").splitlines():
        if line.startswith("markers"):
            in_markers = True
            continue
        if in_markers:
            if line and not line[0].isspace():
                in_markers = False
                continue
            name = line.strip().split(":", 1)[0].strip()
            if name:
                registered.add(name)
    for conftest in TESTS_DIR.rglob("conftest.py"):
        text = conftest.read_text(encoding="utf-8")
        registered.update(re.findall(r'"markers",\s*"([A-Za-z_][A-Za-z0-9_]*)', text))
    return registered


def _markers_carried_by_tests() -> set[str]:
    """Marker names that appear in a `pytestmark`, a decorator, or `mark`."""
    carried = set()
    for path in TESTS_DIR.rglob("test_*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        carried.update(re.findall(r"pytest\.mark\.([A-Za-z_][A-Za-z0-9_]*)", text))
    return carried


@pytest.fixture(scope="module")
def marker_sets() -> list[tuple[str, str, str]]:
    return _workflow_marker_sets()


def test_the_survey_found_the_gates(marker_sets) -> None:
    """Exact rather than a lower bound: RFC-0028 §3.2 requires set equality.

    Measured 2026-09-12: ten marker-driven workflows. The previous `>= 3` let the
    survey shrink to a third of that while the guard still passed, and every
    assertion below would have kept passing over a much smaller surface.
    """
    assert len(marker_sets) == 10, (
        f"expected 10 marker-driven workflows, found {len(marker_sets)}; update "
        "this constant deliberately if the workflow set changed, otherwise the "
        "parser broke and this gate no longer looks at anything"
    )
    templated = [entry for entry in marker_sets if "$" in entry[2]]
    assert {entry[2] for entry in templated} <= {"e2e${EXTRA_MARKS}"}, (
        "a new shell-templated marker set appeared; it cannot be checked "
        f"statically and needs an explicit decision: {templated}"
    )


def test_every_workflow_marker_set_is_registered(marker_sets) -> None:
    """`--strict-markers` rejects an unknown marker, so a typo fails the job.

    Checked here as well because a marker registered in one place and used in a
    workflow is the contract this item is about; the failure should name the
    workflow and job, not surface as a collection error in CI.
    """
    registered = _registered_markers()
    unknown: list[str] = []
    for workflow, job, expression in marker_sets:
        for token in _MARKER_NAME.findall(_resolvable(expression)):
            if token in _KEYWORDS or token in registered:
                continue
            unknown.append(
                f"{workflow}:{job} uses marker {token!r} in -m {expression!r}"
            )
    assert unknown == [], (
        "these gates run under a marker nothing registers:\n  " + "\n  ".join(unknown)
    )


def test_every_positive_marker_is_carried_by_a_test(marker_sets) -> None:
    """The vacuity case: a job whose marker set selects nothing always passes."""
    carried = _markers_carried_by_tests()
    empty: list[str] = []
    for workflow, job, expression in marker_sets:
        expression = _resolvable(expression)
        for token in _MARKER_NAME.findall(_resolvable(expression)):
            if token in _KEYWORDS:
                continue
            # Only positive markers select tests; `not X` is satisfied by absence.
            negated = re.search(rf"not\s+{re.escape(token)}\b", expression)
            if negated or token in carried:
                continue
            empty.append(
                f"{workflow}:{job} selects on {token!r}, which no test carries"
            )
    assert empty == [], (
        "these CI gates would collect zero tests and pass:\n  " + "\n  ".join(empty)
    )


def test_every_gate_names_a_job(marker_sets) -> None:
    """§3.2 asks for the job to be named; an unnamed gate cannot be reviewed."""
    unnamed = [entry for entry in marker_sets if not entry[1].strip()]
    assert unnamed == [], f"marker sets found without an enclosing job key: {unnamed}"
