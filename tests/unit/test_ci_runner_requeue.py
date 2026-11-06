"""Runner-stranded CI runs are re-queued, real failures are not (scripts/ci_runner_requeue.py)."""

from __future__ import annotations

from typing import Any

import pytest

from scripts import ci_runner_requeue
from scripts.ci_runner_requeue import GATE_JOB, MAX_ATTEMPTS, decide, is_stranded, main

REPO = "owner/repo"
RUN_ID = 42075950677
# Messages copied from the check-run annotations of the stranded jobs.
NOT_ACQUIRED = (
    "The job was not acquired by Runner of type hosted even after multiple attempts"
)
CAPACITY = (
    "Due to capacity constraints, jobs targeting macOS arm64 runners may "
    "experience longer queue times."
)
SUPERSEDED = (
    "Canceling since a higher priority waiting request for CI-refs/pull/1/merge exists"
)


def _job(
    job_id: int, name: str, conclusion: str, *, ran: bool = True
) -> dict[str, Any]:
    return {
        "id": job_id,
        "name": name,
        "conclusion": conclusion,
        "steps": [{"name": "Set up job"}] if ran else [],
        "runner_name": "GitHub Actions 1000176770" if ran else "",
    }


def _run(**overrides: Any) -> dict[str, Any]:
    run: dict[str, Any] = {
        "id": RUN_ID,
        "conclusion": "failure",
        "run_attempt": 1,
        "workflow_id": 7,
        "head_branch": "develop",
        "event": "push",
    }
    run.update(overrides)
    return run


STRANDED = _job(
    1, "Test Suite / Test Suite (full) (macos-latest, 3.11, 1)", "cancelled", ran=False
)
GATE = _job(2, GATE_JOB, "failure")
PASSED = _job(3, "Test Suite / Test Suite (full) (macos-latest, 3.11, 2)", "success")
SKIPPED = _job(4, "Build Verification", "skipped", ran=False)


def test_stranded_requires_the_not_acquired_annotation() -> None:
    assert is_stranded(STRANDED, [CAPACITY, NOT_ACQUIRED])
    # A concurrency cancel or a manual cancel looks the same structurally.
    assert not is_stranded(STRANDED, [SUPERSEDED, CAPACITY])
    assert not is_stranded(STRANDED, [])
    ran_then_cancelled = _job(5, "x", "cancelled", ran=True)
    assert not is_stranded(ran_then_cancelled, [NOT_ACQUIRED])


def test_requeues_when_only_runner_acquisition_failed() -> None:
    decision = decide(
        _run(), [STRANDED, GATE, PASSED, SKIPPED], {1: [NOT_ACQUIRED, CAPACITY]}, RUN_ID
    )
    assert decision.requeue
    assert decision.stranded == (STRANDED["name"],)


def test_real_failure_is_never_rerun_away() -> None:
    failed = _job(
        6, "Test Suite / Test Suite (full) (macos-latest, 3.12, 1)", "failure"
    )
    decision = decide(_run(), [STRANDED, failed, GATE], {1: [NOT_ACQUIRED]}, RUN_ID)
    assert not decision.requeue
    assert "real failures present" in decision.reason
    assert failed["name"] in decision.reason


def test_concurrency_cancel_is_not_mistaken_for_a_stranded_job() -> None:
    decision = decide(_run(), [STRANDED, GATE], {1: [SUPERSEDED]}, RUN_ID)
    assert not decision.requeue


@pytest.mark.parametrize(
    ("run", "latest", "why"),
    [
        (_run(conclusion="cancelled"), RUN_ID, "not failure"),
        (_run(conclusion="success"), RUN_ID, "not failure"),
        (_run(run_attempt=MAX_ATTEMPTS), RUN_ID, "reached the limit"),
        (_run(), RUN_ID + 1, "superseded"),
        (_run(), None, "superseded"),
    ],
)
def test_guards_block_the_requeue(
    run: dict[str, Any], latest: int | None, why: str
) -> None:
    decision = decide(run, [STRANDED, GATE], {1: [NOT_ACQUIRED]}, latest)
    assert not decision.requeue
    assert why in decision.reason


def test_failure_without_stranded_jobs_is_left_alone() -> None:
    decision = decide(_run(), [GATE, PASSED], {}, RUN_ID)
    assert not decision.requeue
    assert decision.reason == "no job was stranded without a runner"


class FakeGh:
    """Serves canned ``gh api`` responses and records every call."""

    def __init__(
        self, jobs: list[dict[str, Any]], notes: dict[int, list[str]], latest: int
    ) -> None:
        self.jobs = jobs
        self.notes = notes
        self.latest = latest
        self.calls: list[tuple[str, str]] = []

    def __call__(self, path: str, method: str) -> Any:
        self.calls.append((path, method))
        if path == f"repos/{REPO}/actions/runs/{RUN_ID}":
            return _run()
        if path.startswith(f"repos/{REPO}/actions/runs/{RUN_ID}/attempts/1/jobs"):
            return {"jobs": self.jobs}
        if path.startswith(f"repos/{REPO}/check-runs/"):
            job_id = int(path.split("/")[-2])
            return [{"message": m} for m in self.notes.get(job_id, [])]
        if path.startswith(
            f"repos/{REPO}/actions/workflows/7/runs?branch=develop&event=push"
        ):
            return {"workflow_runs": [{"id": self.latest}]}
        if path.endswith("/rerun-failed-jobs"):
            return None
        raise AssertionError(f"unexpected gh call {method} {path}")


def _posted(gh: FakeGh) -> list[str]:
    return [path for path, method in gh.calls if method == "POST"]


def test_main_reruns_failed_jobs_and_writes_summary(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    gh = FakeGh([STRANDED, GATE, PASSED], {1: [NOT_ACQUIRED]}, RUN_ID)
    assert main(["--repo", REPO, "--run-id", str(RUN_ID)], gh=gh) == 0
    assert _posted(gh) == [f"repos/{REPO}/actions/runs/{RUN_ID}/rerun-failed-jobs"]
    # Annotations are fetched only for jobs that never ran.
    assert [p for p, _ in gh.calls if "check-runs" in p] == [
        f"repos/{REPO}/check-runs/1/annotations"
    ]
    text = summary.read_text(encoding="utf-8")
    assert STRANDED["name"] in text and "Re-ran failed jobs." in text
    assert "Re-ran failed jobs." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("argv_extra", "latest"),
    [(["--dry-run"], RUN_ID), ([], RUN_ID + 1)],
)
def test_main_does_not_post_on_dry_run_or_superseded(
    argv_extra: list[str], latest: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    gh = FakeGh([STRANDED, GATE], {1: [NOT_ACQUIRED]}, latest)
    assert main(["--repo", REPO, "--run-id", str(RUN_ID), *argv_extra], gh=gh) == 0
    assert _posted(gh) == []


def test_gh_api_runs_the_gh_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    class Done:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    def fake_run(argv: list[str], **_: Any) -> Done:
        seen.append(argv)
        return Done('{"id": 1}' if argv[3] == "GET" else "")

    monkeypatch.setattr(ci_runner_requeue.subprocess, "run", fake_run)
    assert ci_runner_requeue._gh_api("repos/x", "GET") == {"id": 1}
    assert ci_runner_requeue._gh_api("repos/x/rerun", "POST") is None
    assert seen == [
        ["gh", "api", "--method", "GET", "repos/x"],
        ["gh", "api", "--method", "POST", "repos/x/rerun"],
    ]
