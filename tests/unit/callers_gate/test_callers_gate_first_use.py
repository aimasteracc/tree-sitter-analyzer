"""Friction found by the first real use of the gate (PR #1887).

* results of a later run on the same tree must not overwrite an earlier run's;
  promote picks one run explicitly;
* ``--jobs 1`` is strictly sequential;
* ``--fresh-base`` recomputes base sides (fair base-vs-head timings);
* a missing / null check result on one side is budget noise to re-ask;
* every changed row shows the head's finding and ``next_step``.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import answers, report, runner
from benchmarks.callers_gate.layout import REPOS, Layout
from benchmarks.callers_gate.transitions import diff_repo

KEY = answers.AnswerKey("t" * 40, "k" * 24, "rich", "s" * 40, "q" * 24)
TARGET = {"mode": "bare", "file": "a.py", "qual": "A.f", "name": "A.f"}


def _rows(completeness: str, ncr: Any = 0, next_step: str = "") -> list[dict[str, Any]]:
    full: dict[str, Any] = {
        "completeness": completeness,
        "completeness_reasons": [],
        "callers": [],
        "non_call_reference_sites": [],
        "next_step": next_step,
    }
    if ncr != "missing":
        full["non_call_references"] = ncr
    return [{**TARGET, "full": full, "compact": {"completeness": completeness}}]


def _quiet(_m: str) -> None:
    return None


def test_a_later_run_never_overwrites_an_earlier_runs_results(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    first = layout.result(KEY.tree, KEY.index_key, "rich", "20260101-000000")
    second = layout.result(KEY.tree, KEY.index_key, "rich", "20260102-000000")
    answers.write_answers(first, KEY, _rows("complete"), "computed")
    answers.write_answers(second, KEY, _rows("incomplete"), "computed")
    assert first.is_file() and second.is_file() and first != second
    # disagreeing runs: nothing is promoted without an explicit choice
    assert answers.promote(layout, KEY.tree, _quiet) == []
    copied = answers.promote(layout, KEY.tree, _quiet, run_id="20260101-000000")
    assert answers.read_answers(copied[0], KEY, _quiet) == _rows("complete")


def test_agreeing_runs_promote_without_a_choice(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    for run_id in ("r1", "r2"):
        answers.write_answers(
            layout.result(KEY.tree, KEY.index_key, "rich", run_id),
            KEY,
            _rows("complete"),
            "computed",
        )
    assert answers.promote(layout, KEY.tree, _quiet) == [
        layout.baseline(KEY.tree, KEY.index_key, "rich")
    ]


def _ctx(tmp_path: Path, **kw: Any) -> runner.RunContext:
    return runner.RunContext(
        layout=Layout(tmp_path),
        python=Path("py"),
        base=None,  # type: ignore[arg-type]
        head=None,  # type: ignore[arg-type]
        git_dir=tmp_path,
        env_key="e",
        manifest={},
        run_dir=tmp_path / "run-1",
        shards={"zod": 5, "hono": 2},
        log=_quiet,
        **kw,
    )


def test_jobs_1_runs_repos_one_after_another_with_one_server_per_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    active, overlap, seen_shards = [0], [False], []
    lock = threading.Lock()

    def fake(ctx: runner.RunContext, pin: Any) -> runner.RepoRun:
        with lock:
            active[0] += 1
            overlap[0] = overlap[0] or active[0] > 1
        seen_shards.append(ctx.shards.get(pin.name, 1))
        time.sleep(0.02)
        with lock:
            active[0] -= 1
        return runner.RepoRun(pin.name, error="stub")

    monkeypatch.setattr(runner, "run_repo", fake)
    ctx = _ctx(tmp_path)
    runner.run_all(ctx, list(REPOS), jobs=1)
    assert not overlap[0]
    assert seen_shards == [1] * len(REPOS)


def test_fresh_base_ignores_cached_answers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(runner, "_cached_answers", lambda *a: _rows("complete"))

    def compute(**kw: Any) -> tuple[list[dict[str, Any]], float]:
        calls.append(kw["label"])
        return _rows("incomplete"), 1.5

    monkeypatch.setattr(runner, "compute_side", compute)
    monkeypatch.setattr(runner.RunContext, "pkg", lambda self, side: tmp_path)
    side = type("S", (), {"tree": "t" * 40})()
    pin = REPOS["rich"]
    for fresh, expect in ((False, "cache"), (True, "computed")):
        rows, source, _secs = runner._side_answers(
            _ctx(tmp_path, fresh_base=fresh),
            pin,
            label="base",
            side=side,  # type: ignore[arg-type]
            key=KEY,
            root=lambda: tmp_path,
            targets=[TARGET],
        )
        assert source == expect
    assert calls == ["rich-base"]


def test_a_null_check_result_on_one_side_is_re_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = _rows("incomplete", ncr=None)
    base = _rows("incomplete", ncr=3)
    head[0]["full"]["non_call_reference_sites"] = [
        {"file": "b.py", "line": 1, "callee": None}
    ]
    assert not runner.budget_limited(head[0])  # no *_UNCHECKED, forms agree
    assert runner.pair_limited(base[0], head[0])
    asked: list[str] = []

    def fake(**kw: Any) -> tuple[list[dict[str, Any]], float]:
        asked.append(kw["label"])
        return _rows("incomplete", ncr=3), 0.1

    monkeypatch.setattr(runner, "compute_side", fake)
    run = runner.RepoRun(
        "fastapi", index_key="k", root=tmp_path, base_rows=base, head_rows=head
    )
    run.retry_context = {
        "targets": [TARGET],
        "base": (tmp_path, tmp_path, tmp_path / "b.json", KEY),
        "head": (tmp_path, tmp_path, tmp_path / "h.json", KEY),
    }
    runner.retry_budget_rows(_ctx(tmp_path), run)
    assert asked == ["fastapi-head-retry1"]  # only the side that lost the result
    assert run.head_rows[0]["full"]["non_call_references"] == 3
    assert diff_repo("fastapi", run.base_rows, run.head_rows).changes == []


def test_every_changed_row_shows_the_heads_finding_and_next_step() -> None:
    diff = diff_repo(
        "rich",
        _rows("incomplete"),
        _rows("complete", next_step="read b.py:3 then stop"),
    )
    comparison = report._comparison(diff, "x")
    text = "\n".join(
        report._evidence([{"repo": "rich", "comparisons": {"same_index": comparison}}])
    )
    assert "next_step: read b.py:3 then stop" in text
    assert "finding: complete" in text
