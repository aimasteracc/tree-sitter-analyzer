"""Pin the CI runner re-queue contract.

A macos-latest job that no hosted runner acquires is cancelled by GitHub
with zero steps; the fail-closed Quality Gate then fails a run in which no
test failed. ci-runner-requeue.yml re-runs such runs (see
scripts/ci_runner_requeue.py); this pins how it is wired.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scripts import ci_runner_requeue

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
REQUEUE = WORKFLOWS / "ci-runner-requeue.yml"


def _load(path: Path) -> dict[Any, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_requeue_follows_completed_ci_runs() -> None:
    workflow = _load(REQUEUE)
    ci_name = _load(WORKFLOWS / "ci.yml")["name"]
    # PyYAML reads the bare ``on`` key as True.
    trigger = workflow.get("on", workflow.get(True))
    assert trigger == {"workflow_run": {"workflows": [ci_name], "types": ["completed"]}}


def test_requeue_has_least_privilege_and_runs_trusted_code_only() -> None:
    workflow = _load(REQUEUE)
    assert workflow["permissions"] == {
        "actions": "write",
        "checks": "read",
        "contents": "read",
    }
    (job,) = workflow["jobs"].values()
    assert job["timeout-minutes"] <= 5
    checkout = job["steps"][0]
    assert checkout["uses"].startswith("actions/checkout@")
    # Default-branch checkout of the script only; never the triggering head.
    assert "ref" not in checkout.get("with", {})
    assert checkout["with"]["sparse-checkout"] == "scripts/ci_runner_requeue.py"
    run = job["steps"][1]["run"]
    assert "scripts/ci_runner_requeue.py" in run
    assert "--dry-run" not in run


def test_requeue_attempt_bound_matches_the_script() -> None:
    (job,) = _load(REQUEUE)["jobs"].values()
    condition = job["if"]
    assert "github.event.workflow_run.conclusion == 'failure'" in condition
    assert (
        f"github.event.workflow_run.run_attempt < {ci_runner_requeue.MAX_ATTEMPTS}"
        in condition
    )


def test_requeue_exempts_only_the_required_gate_job() -> None:
    gate = _load(WORKFLOWS / "ci.yml")["jobs"]["quality-gate"]
    assert gate["name"] == ci_runner_requeue.GATE_JOB == "Quality Gate"
