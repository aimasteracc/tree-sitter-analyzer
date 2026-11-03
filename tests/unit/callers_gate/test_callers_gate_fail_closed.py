"""Fail-closed caches and ground truth: nothing corrupt, stale or missing can produce a pass."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import answers, corpus, gitutil, index_store
from benchmarks.callers_gate.layout import REPOS, Layout
from benchmarks.callers_gate.oracle_truth import check_rows

ROWS = [
    {
        "mode": "bare",
        "file": "a.py",
        "qual": "A.f",
        "name": "A.f",
        "full": {"completeness": "complete", "callers": []},
        "compact": {"completeness": "complete"},
        "seconds": 0.5,
        "bytes": 10,
        "compact_bytes": 5,
    }
]
KEY = answers.AnswerKey("t" * 40, "k" * 24, "rich", "s" * 40, "q" * 24)


def _quiet(_msg: str) -> None:
    return None


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "baseline" / KEY.tree / KEY.index_key / "rich.json"
    answers.write_answers(path, KEY, ROWS, "computed")
    return path


def test_a_valid_answer_file_round_trips(tmp_path: Path) -> None:
    path = _write(tmp_path)
    assert answers.read_answers(path, KEY, _quiet) == ROWS


def test_timings_are_not_part_of_the_digest() -> None:
    other = [{**ROWS[0], "seconds": 9.0, "bytes": 99}]
    assert answers.rows_digest(other) == answers.rows_digest(ROWS)


def test_corrupt_json_is_quarantined_and_misses(tmp_path: Path) -> None:
    path = _write(tmp_path)
    path.write_text(path.read_text(encoding="utf-8")[:-20], encoding="utf-8")
    assert answers.read_answers(path, KEY, _quiet) is None
    assert not path.exists()
    assert len(list(path.parent.glob("rich.json.*.corrupt"))) == 1


def test_tampered_rows_fail_the_digest(tmp_path: Path) -> None:
    path = _write(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rows"][0]["full"]["completeness"] = "incomplete"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert answers.read_answers(path, KEY, _quiet) is None


@pytest.mark.parametrize(
    "field", ["tree", "index_key", "repo", "repo_sha", "query_key"]
)
def test_any_identity_mismatch_misses(tmp_path: Path, field: str) -> None:
    path = _write(tmp_path)
    wrong = answers.AnswerKey(**{**KEY.__dict__, field: "x"})
    assert answers.read_answers(path, wrong, _quiet) is None


def test_a_file_copied_under_another_tree_is_not_used(tmp_path: Path) -> None:
    path = _write(tmp_path)
    other = tmp_path / "baseline" / ("u" * 40) / KEY.index_key / "rich.json"
    other.parent.mkdir(parents=True)
    other.write_bytes(path.read_bytes())
    moved = answers.AnswerKey(**{**KEY.__dict__, "tree": "u" * 40})
    assert answers.read_answers(other, moved, _quiet) is None


def test_promote_copies_only_validated_results(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    answers.write_answers(
        layout.result(KEY.tree, KEY.index_key, "rich"), KEY, ROWS, "computed"
    )
    broken = layout.result(KEY.tree, KEY.index_key, "gson")
    broken.write_text("{}", encoding="utf-8")
    copied = answers.promote(layout, KEY.tree, _quiet)
    assert copied == [layout.baseline(KEY.tree, KEY.index_key, "rich")]
    assert answers.read_answers(copied[0], KEY, _quiet) == ROWS
    assert answers.promote(layout, "z" * 40, _quiet) == []


def test_index_manifest_must_name_this_key_and_be_ready(tmp_path: Path) -> None:
    pin = REPOS["gson"]
    directory = tmp_path / "k1"
    (directory / "tree" / ".ast-cache").mkdir(parents=True)
    manifest = {
        "format": 1,
        "key": "k1",
        "repo": "gson",
        "repo_sha": pin.sha,
        "status": "ready",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert index_store.read_manifest(directory, "k1", pin) is not None
    assert index_store.read_manifest(directory, "k2", pin) is None
    (directory / "manifest.json").write_text(
        json.dumps({**manifest, "status": "building"}), encoding="utf-8"
    )
    assert index_store.read_manifest(directory, "k1", pin) is None
    (directory / "manifest.json").write_text("garbage", encoding="utf-8")
    assert index_store.read_manifest(directory, "k1", pin) is None


def test_missing_ground_truth_raises(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    with pytest.raises(corpus.CorpusError, match="ground truth missing"):
        corpus.load_json_truth(layout.gt2("rich"), {"gt2/rich.json": "x"}, layout)
    with pytest.raises(corpus.CorpusError, match="manifest unreadable"):
        corpus.verify_corpus(layout)


def test_a_corpus_file_edited_after_setup_is_refused(tmp_path: Path) -> None:
    layout = Layout(tmp_path)
    target = layout.targets("rich")
    target.parent.mkdir(parents=True)
    target.write_text("[]", encoding="utf-8")
    (layout.corpus / "manifest.json").write_text(
        json.dumps({"targets/rich.json": corpus.sha256_file(target)}), encoding="utf-8"
    )
    assert corpus.verify_corpus(layout) == {
        "targets/rich.json": corpus.sha256_file(target)
    }
    target.write_text("[1]", encoding="utf-8")
    with pytest.raises(corpus.CorpusError, match="changed since setup"):
        corpus.verify_corpus(layout)


def _gt2() -> dict[str, Any]:
    return {
        "callers": {"a.py::A.f": [["b.py", "g", 10, "bare", 12]]},
        "module_callers": {},
        "defs": [{"key": "a.py::A.f"}, {"key": "a.py::A.h"}],
    }


def _truth_row(
    qual: str, completeness: str, callers: list[dict[str, Any]], **full: Any
) -> dict[str, Any]:
    return {
        "mode": "bare",
        "file": "a.py",
        "qual": qual,
        "full": {"completeness": completeness, "callers": callers, **full},
    }


def test_gt2_miss_on_a_new_complete_fails_and_on_an_unchanged_row_is_preexisting() -> (
    None
):
    rows = [_truth_row("A.f", "complete", [])]
    result = check_rows("rich", rows, set(), gt2=_gt2(), labels=None)
    assert [f["kind"] for f in result["failures"]] == ["gt2_miss"]
    assert result["failures"][0]["detail"] == [["b.py", "g", 10, 12]]
    again = check_rows("rich", rows, {("bare", "a.py", "A.f")}, gt2=_gt2(), labels=None)
    assert again["failures"] == []
    assert [f["kind"] for f in again["preexisting"]] == ["gt2_miss"]


def test_gt2_pass_untracked_target_and_open_sites() -> None:
    listed = [
        _truth_row("A.f", "complete", [{"file": "b.py", "name": "g", "line": 10}])
    ]
    assert check_rows("rich", listed, set(), gt2=_gt2(), labels=None)["failures"] == []
    untracked = [_truth_row("A.z", "complete", [])]
    assert [
        f["kind"]
        for f in check_rows("rich", untracked, set(), gt2=_gt2(), labels=None)[
            "failures"
        ]
    ] == ["gt2_untracked"]
    bound = {"enumerated": True, "fields": ["unresolved_sites"], "total": 1}
    sound = [
        _truth_row(
            "A.f",
            "unknown",
            [],
            open_sites=bound,
            unresolved_sites=[{"file": "b.py", "line": 12}],
        )
    ]
    assert check_rows("rich", sound, set(), gt2=_gt2(), labels=None)["failures"] == []
    unsound = [
        _truth_row(
            "A.f",
            "unknown",
            [],
            open_sites=bound,
            unresolved_sites=[{"file": "b.py", "line": 99}],
        )
    ]
    assert [
        f["kind"]
        for f in check_rows("rich", unsound, set(), gt2=_gt2(), labels=None)["failures"]
    ] == ["open_sites_gt2_miss"]


def test_label_misses_on_complete_and_enumerated_answers() -> None:
    labels = {"f": {"file": "a.py", "calls": [["c.ts", 5]], "refs": [["c.ts", 9]]}}
    rows = [_truth_row("A.f", "complete", [])]
    result = check_rows("hono", rows, set(), gt2=None, labels=labels)
    assert [f["kind"] for f in result["failures"]] == ["label_call_miss"]
    ok = [
        _truth_row(
            "A.f",
            "complete",
            [{"file": "c.ts", "name": "g", "line": 1, "end_line": 20}],
        )
    ]
    assert check_rows("hono", ok, set(), gt2=None, labels=labels)["failures"] == []


@pytest.mark.slow_ok  # several real git subprocesses
def test_worktree_tree_hash_sees_uncommitted_edits(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    (repo / gitutil.PACKAGE).mkdir(parents=True)
    (repo / gitutil.PACKAGE / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["add", "."],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    committed = gitutil.ref_tree(repo, "HEAD")
    assert gitutil.worktree_tree(repo) == committed
    (repo / gitutil.PACKAGE / "__init__.py").write_text("x = 2\n", encoding="utf-8")
    dirty = gitutil.worktree_tree(repo)
    assert dirty != committed
    (repo / gitutil.PACKAGE / "new.py").write_text("y = 1\n", encoding="utf-8")
    assert gitutil.worktree_tree(repo) not in (committed, dirty)
    assert gitutil.git(repo, "status", "--porcelain").strip() != ""
    assert gitutil.git(repo, "diff", "--cached", "--name-only").strip() == ""
