#!/usr/bin/env python3
"""Re-queue a CI run whose only failure is a hosted runner that never came.

GitHub cancels a queued job when no hosted runner acquires it in time. The
job then ends ``cancelled`` with no runner and no steps, and its check run
carries the annotation ``The job was not acquired by Runner of type hosted
even after multiple attempts``. That has hit macos-latest (arm64) lanes on
develop and on PRs while GitHub reported macOS arm64 capacity constraints;
no test ran, yet the fail-closed ``Quality Gate`` turned the commit red.

The gate must stay fail-closed (a lane that never ran proves nothing), so
this script asks GitHub to re-run the failed jobs instead -- but only when:

* the run concluded ``failure`` and is below ``MAX_ATTEMPTS``;
* at least one job is *stranded*: ``cancelled``, zero steps, no runner, and
  its check run carries the not-acquired annotation;
* every other failed / cancelled job is the ``Quality Gate`` itself, so a
  real test failure is never re-run away;
* the run is still the newest CI run for its branch and event. ci.yml
  cancels in-progress runs of the same ref, so re-running a superseded run
  could cancel the newer one.

Stdlib only; talks to GitHub through the ``gh`` CLI (``GH_TOKEN``).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404 - fixed argv to the gh CLI, no shell
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Automatic re-queues stop once a run reaches this attempt number.
MAX_ATTEMPTS = 3

#: Check-run annotation GitHub writes when no hosted runner took the job.
NOT_ACQUIRED = "was not acquired by Runner"

#: The required gate job of ci.yml; it fails *because of* stranded lanes.
GATE_JOB = "Quality Gate"

_BAD = frozenset({"failure", "cancelled", "timed_out", "startup_failure"})

GhApi = Callable[[str, str], Any]


@dataclass(frozen=True)
class Decision:
    requeue: bool
    reason: str
    stranded: tuple[str, ...] = field(default_factory=tuple)


def is_stranded(job: Mapping[str, Any], annotations: Sequence[str]) -> bool:
    """A job GitHub cancelled because no hosted runner acquired it."""
    return (
        job.get("conclusion") == "cancelled"
        and not job.get("steps")
        and not job.get("runner_name")
        and any(NOT_ACQUIRED in message for message in annotations)
    )


def decide(
    run: Mapping[str, Any],
    jobs: Sequence[Mapping[str, Any]],
    annotations: Mapping[int, Sequence[str]],
    latest_run_id: int | None,
    max_attempts: int = MAX_ATTEMPTS,
) -> Decision:
    """Whether to re-run the failed jobs of ``run``."""
    if run.get("conclusion") != "failure":
        return Decision(False, f"run concluded {run.get('conclusion')!r}, not failure")
    attempt = int(run.get("run_attempt") or 1)
    if attempt >= max_attempts:
        return Decision(False, f"attempt {attempt} reached the limit {max_attempts}")
    if latest_run_id != run.get("id"):
        return Decision(False, f"superseded by newer run {latest_run_id}")

    stranded: list[str] = []
    real: list[str] = []
    for job in jobs:
        if job.get("conclusion") not in _BAD:
            continue
        name = str(job.get("name", "?"))
        if is_stranded(job, annotations.get(int(job.get("id", 0)), ())):
            stranded.append(name)
        elif name != GATE_JOB:
            real.append(f"{name} ({job.get('conclusion')})")
    if real:
        return Decision(False, "real failures present: " + "; ".join(real))
    if not stranded:
        return Decision(False, "no job was stranded without a runner")
    return Decision(True, "only runner-acquisition cancellations", tuple(stranded))


def _gh_api(path: str, method: str = "GET") -> Any:
    completed = subprocess.run(  # nosec B603 - fixed argv, no shell
        ["gh", "api", "--method", method, path],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout) if completed.stdout.strip() else None


def evaluate_run(repo: str, run_id: int, gh: GhApi = _gh_api) -> Decision:
    """Fetch ``run_id`` from GitHub and decide.

    One page is enough: a CI run has well under 100 jobs, and a stranded
    job carries a handful of annotations.
    """
    run = gh(f"repos/{repo}/actions/runs/{run_id}", "GET") or {}
    attempt = int(run.get("run_attempt") or 1)
    jobs_path = f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs"
    jobs = (gh(f"{jobs_path}?per_page=100", "GET") or {}).get("jobs") or []
    annotations: dict[int, list[str]] = {}
    for job in jobs:
        if job.get("conclusion") == "cancelled" and not job.get("steps"):
            notes = gh(f"repos/{repo}/check-runs/{job['id']}/annotations", "GET") or []
            annotations[int(job["id"])] = [str(n.get("message", "")) for n in notes]
    newest_path = (
        f"repos/{repo}/actions/workflows/{run.get('workflow_id')}/runs"
        f"?branch={run.get('head_branch')}&event={run.get('event')}&per_page=1"
    )
    newest = (gh(newest_path, "GET") or {}).get("workflow_runs") or []
    latest_run_id = int(newest[0]["id"]) if newest else None
    return decide(run, jobs, annotations, latest_run_id)


def render(run_id: int, decision: Decision, requeued: bool) -> str:
    lines = [
        f"### CI runner re-queue (run {run_id})",
        "",
        f"- Decision: {decision.reason}",
    ]
    lines += [f"- Stranded (no runner acquired): {name}" for name in decision.stranded]
    lines.append("- Re-ran failed jobs." if requeued else "- No re-run.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None, gh: GhApi = _gh_api) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--dry-run", action="store_true", help="decide, do not re-run")
    args = parser.parse_args(argv)

    decision = evaluate_run(args.repo, args.run_id, gh)
    requeued = False
    if decision.requeue and not args.dry_run:
        gh(f"repos/{args.repo}/actions/runs/{args.run_id}/rerun-failed-jobs", "POST")
        requeued = True
    report = render(args.run_id, decision, requeued)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
