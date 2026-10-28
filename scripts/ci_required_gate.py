#!/usr/bin/env python3
"""Fail-closed required gate for ci.yml (the ``Quality Gate`` check).

The route job decides which lanes a change needs. This gate derives the
required lanes from the route's own outputs and then demands:

* the route job itself succeeded and emitted every routing flag as an
  explicit ``true`` / ``false`` (a missing flag is a misfire, not "off");
* every **selected** lane finished with ``success`` -- ``skipped``,
  ``cancelled``, ``failure`` or a lane absent from ``needs`` all fail;
* a lane that was **not** selected is ``skipped`` (or ``success``); a
  ``failure`` or ``cancelled`` result still fails the gate;
* something substantive was selected (the test matrix or the docs check).

Before this gate a selected lane that ended ``skipped`` (for example because
an upstream job it ``needs`` was skipped by an ``if:`` typo) passed silently.

Input: ``CI_NEEDS`` -- ``${{ toJSON(needs) }}`` of the gate job. Stdlib only:
it runs before project dependencies are installed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROUTE_JOB = "route"

#: Every lane the gate ``needs`` -> the route output that selects it.
LANES: Mapping[str, str] = {
    "docs-check": "run_docs_check",
    "quality-check": "run_quality",
    "test": "run_test_matrix",
    "build": "run_build",
    "e2e": "run_e2e_smoke",
    "regression": "run_regression",
    "sql-platform-compat": "run_sql_platform_compat",
    "test-quality-audit": "run_test_matrix",
}

#: At least one of these lanes must be selected: a run that selects neither
#: the test matrix nor the docs check validated nothing.
SUBSTANTIVE_LANES: tuple[str, ...] = ("test", "docs-check")

_UNSELECTED_OK = frozenset({"skipped", "success"})


@dataclass(frozen=True)
class LaneVerdict:
    lane: str
    selected: bool | None
    result: str
    ok: bool
    why: str


def evaluate(needs: Mapping[str, Any]) -> tuple[list[LaneVerdict], list[str]]:
    """Per-lane verdicts and the gate-level errors for ``needs``."""
    errors: list[str] = []
    route = needs.get(ROUTE_JOB)
    route_result = _result(route)
    if route_result != "success":
        errors.append(f"route job did not succeed: {route_result}")
    outputs = route.get("outputs") if isinstance(route, Mapping) else None
    if not isinstance(outputs, Mapping):
        outputs = {}

    verdicts: list[LaneVerdict] = []
    for lane, flag in LANES.items():
        value = outputs.get(flag)
        result = _result(needs.get(lane))
        if value not in ("true", "false"):
            verdicts.append(
                LaneVerdict(lane, None, result, False, f"route output {flag}={value!r}")
            )
            continue
        selected = value == "true"
        if selected:
            ok = result == "success"
            why = "selected" if ok else f"selected but {result}"
        else:
            ok = result in _UNSELECTED_OK
            why = "not selected" if ok else f"not selected but {result}"
        verdicts.append(LaneVerdict(lane, selected, result, ok, why))

    unknown = sorted(set(needs) - set(LANES) - {ROUTE_JOB})
    if unknown:
        errors.append(
            f"jobs in needs without a lane mapping: {', '.join(unknown)} "
            "(add them to LANES in scripts/ci_required_gate.py)"
        )
    if not any(v.selected for v in verdicts if v.lane in SUBSTANTIVE_LANES):
        errors.append(
            "neither the test matrix nor the docs check was selected (route misfire?)"
        )
    return verdicts, errors


def _result(job: Any) -> str:
    if not isinstance(job, Mapping):
        return "missing"
    result = job.get("result")
    return result if isinstance(result, str) and result else "missing"


def render(verdicts: list[LaneVerdict], errors: list[str]) -> str:
    passed = not errors and all(v.ok for v in verdicts)
    lines = [
        "### Quality Gate (fail-closed)",
        "",
        "| Lane | Selected | Result | Verdict |",
        "| --- | --- | --- | --- |",
    ]
    for v in verdicts:
        selected = {True: "yes", False: "no", None: "?"}[v.selected]
        mark = "pass" if v.ok else "FAIL"
        lines.append(f"| {v.lane} | {selected} | {v.result} | {mark}: {v.why} |")
    lines.append("")
    lines += [f"- FAIL: {error}" for error in errors]
    lines.append(
        "All selected lanes passed." if passed else "Quality Gate rejected this run."
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--needs-file", help="read toJSON(needs) from a file instead of $CI_NEEDS"
    )
    args = parser.parse_args(argv)
    raw = (
        Path(args.needs_file).read_text(encoding="utf-8")
        if args.needs_file
        else os.environ.get("CI_NEEDS", "")
    )
    try:
        needs = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"CI_NEEDS is not JSON: {error}", file=sys.stderr)
        return 1
    if not isinstance(needs, dict):
        print("CI_NEEDS must be a JSON object", file=sys.stderr)
        return 1
    verdicts, errors = evaluate(needs)
    report = render(verdicts, errors)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report)
    return 0 if not errors and all(v.ok for v in verdicts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
