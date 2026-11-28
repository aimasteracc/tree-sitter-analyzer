"""Budget-limited answers (TSA ``*_UNCHECKED``) are re-asked, never trusted as a change."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import answers, runner

TARGET = {
    "mode": "qualified",
    "file": "src/context.ts",
    "qual": "Context.#newResponse",
    "name": "Context.#newResponse",
}
OTHER = {"mode": "bare", "file": "src/a.ts", "qual": "f", "name": "f"}


def _row(
    target: dict[str, Any],
    completeness: str,
    reasons: list[str],
    compact: str | None = None,
) -> dict[str, Any]:
    return {
        **target,
        "full": {
            "completeness": completeness,
            "completeness_reasons": reasons,
            "callers": [],
        },
        "compact": {"completeness": compact or completeness},
        "seconds": 1.0,
    }


def test_budget_limited_recognizes_unchecked_reasons_and_form_disagreement() -> None:
    assert runner.budget_limited(
        _row(TARGET, "incomplete", ["NON_CALL_REFERENCES_UNCHECKED"])
    )
    assert runner.budget_limited(_row(TARGET, "incomplete", ["X"], compact="complete"))
    assert not runner.budget_limited(_row(TARGET, "complete", []))


def _ctx(tmp_path: Path) -> runner.RunContext:
    return runner.RunContext(
        layout=None,
        python=Path("py"),
        base=None,
        head=None,
        git_dir=tmp_path,  # type: ignore[arg-type]
        env_key="e",
        manifest={},
        run_dir=tmp_path,
        shards={},
        log=lambda _m: None,
    )


def _run(tmp_path: Path, head_row: dict[str, Any]) -> runner.RepoRun:
    key = answers.AnswerKey("t" * 40, "k", "hono", "s", "q")
    run = runner.RepoRun("hono", index_key="k", root=tmp_path)
    run.base_rows = [_row(TARGET, "complete", []), _row(OTHER, "complete", [])]
    run.head_rows = [head_row, _row(OTHER, "complete", [])]
    run.retry_context = {
        "targets": [TARGET, OTHER],
        "base": (tmp_path, tmp_path, tmp_path / "base.json", key),
        "head": (tmp_path, tmp_path, tmp_path / "head.json", key),
    }
    return run


def test_a_conclusive_retry_replaces_the_limited_row_and_rewrites_the_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def fake(**kw: Any) -> tuple[list[dict[str, Any]], float]:
        asked.append([t["qual"] for t in kw["targets"]])
        return [_row(TARGET, "complete", [])], 0.1

    monkeypatch.setattr(runner, "compute_side", fake)
    run = _run(
        tmp_path,
        _row(
            TARGET, "incomplete", ["NON_CALL_REFERENCES_UNCHECKED"], compact="complete"
        ),
    )
    runner.retry_budget_rows(_ctx(tmp_path), run)
    assert asked == [
        ["Context.#newResponse"]
    ]  # only the head side was limited; OTHER untouched
    assert run.head_rows[0]["full"]["completeness"] == "complete"
    assert [r["conclusive"] for r in run.retried] == [True]
    assert (
        answers.read_answers(
            tmp_path / "head.json", run.retry_context["head"][3], lambda _m: None
        )
        == run.head_rows
    )


def test_a_row_still_limited_after_all_attempts_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    limited = _row(TARGET, "incomplete", ["NON_CALL_REFERENCES_UNCHECKED"])
    monkeypatch.setattr(runner, "compute_side", lambda **kw: ([limited], 0.1))
    run = _run(tmp_path, limited)
    runner.retry_budget_rows(_ctx(tmp_path), run, attempts=2)
    assert run.head_rows[0] is limited
    assert [(r["attempt"], r["conclusive"]) for r in run.retried] == [
        (1, False),
        (2, False),
    ]
    assert not (tmp_path / "head.json").exists()


def test_unchanged_rows_are_not_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**kw: Any) -> Any:
        raise AssertionError("must not re-ask")

    monkeypatch.setattr(runner, "compute_side", boom)
    run = _run(tmp_path, _row(TARGET, "complete", []))
    runner.retry_budget_rows(_ctx(tmp_path), run)
    assert run.retried == []


# --- #1923: the open_sites bound has budgets of its own ---------------------

_BOUND = {"total": 8, "enumerated": True, "fields": ["unresolved_sites"]}


def _unknown(full_bound: Any, compact_bound: Any) -> dict[str, Any]:
    """The hono ``HonoRequest.addValidatedData`` shape: unknown, an exhaustive
    bound in the full answer, and whatever bound the separate compact call got."""
    row = _row(TARGET, "unknown", ["UNRESOLVED_IN_DECLARING_FILE", "NAME_ONLY_INBOUND"])
    row["full"]["open_sites"] = full_bound
    row["compact"]["open_sites"] = compact_bound
    return row


def test_a_compact_answer_that_lost_the_bound_is_budget_limited() -> None:
    assert runner.budget_limited(_unknown(_BOUND, None))
    assert not runner.budget_limited(_unknown(_BOUND, {"total": 8, "enumerated": True}))
    # A structural non-bound projects to no compact bound: forms agree.
    assert not runner.budget_limited(
        _unknown({"enumerated": False, "reason": "NO_SITE_LIST"}, None)
    )


def test_an_unchecked_bound_is_budget_limited_in_either_form() -> None:
    unchecked = {
        "enumerated": False,
        "reason": "REVIEW_UNCHECKED",
        "unchecked": "NON_CALL_REFERENCES_UNCHECKED",
    }
    assert runner.budget_limited(_unknown(unchecked, unchecked))
    assert runner.budget_limited(_unknown(_BOUND, unchecked))


def test_a_compact_answer_that_lost_the_bound_is_re_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = _unknown(_BOUND, {"total": 8, "enumerated": True})
    monkeypatch.setattr(runner, "compute_side", lambda **kw: ([good], 0.1))
    run = _run(tmp_path, good)
    run.base_rows[0] = _unknown(_BOUND, None)  # the flaky base answer
    runner.retry_budget_rows(_ctx(tmp_path), run)
    assert run.base_rows[0] == good
    assert [(r["side"], r["conclusive"]) for r in run.retried] == [("base", True)]
