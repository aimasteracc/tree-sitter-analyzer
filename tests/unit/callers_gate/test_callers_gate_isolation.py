"""Side isolation: indexer regressions, memo collisions and unaudited index workers.

* Finding 1: base and head used to read only the head-built index, so a change
  to the indexer was invisible. The base answers on the base's own index are
  now a second comparison, and "pre-existing" is judged against it.
* Finding 12: TSA's ``source_fingerprint`` (path + size + mtime) collided for
  two ``git archive`` snapshots extracted in the same second.
* Finding 13: the QUERY_ONLY import audit only saw the index builder process.
"""

from __future__ import annotations

import json
import multiprocessing
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from benchmarks.callers_gate import (
    _boot,
    answers,
    corpus,
    gitutil,
    index_store,
    keys,
    mcp_client,
    report,
    runner,
    sides,
)
from benchmarks.callers_gate.layout import REPOS, Layout
from benchmarks.callers_gate.policy import Policy

PIN = REPOS["rich"]
TARGET = {"mode": "bare", "file": "a.py", "qual": "A.f", "name": "A.f"}


def _row(completeness: str, callers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        **TARGET,
        "full": {
            "completeness": completeness,
            "completeness_reasons": [] if completeness == "complete" else ["R"],
            "caller_count": len(callers),
            "callers": callers,
        },
        "compact": {
            "completeness": completeness,
            "answer": f"callers of A.f: {len(callers)}\nverdict: {completeness}",
        },
        "seconds": 0.1,
    }


def _side(label: str, blobs: dict[str, str], tree: str) -> sides.Side:
    return sides.Side(label, label, tree, Path(f"/pkg/{label}"), blobs, None, None)


BLOBS = {"__init__.py": "a" * 40, "cache/indexer.py": "b" * 40}


def _ctx(tmp_path: Path, base: sides.Side, head: sides.Side) -> runner.RunContext:
    return runner.RunContext(
        layout=Layout(tmp_path),
        python=Path("py"),
        base=base,
        head=head,
        git_dir=tmp_path,
        env_key="env",
        manifest={},
        run_dir=tmp_path / "run",
        shards={},
        log=lambda _m: None,
    )


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    calls: dict[str, Any] = {"indexes": [], "sides": []}

    def ensure_index(layout: Any, pin: Any, key: str, **kw: Any) -> Any:
        calls["indexes"].append((key, str(kw["head_pkg_parent"])))
        return index_store.IndexInfo(key, tmp_path / "index" / key, True, 0.0)

    def compute_side(**kw: Any) -> tuple[list[dict[str, Any]], float]:
        calls["sides"].append((kw["label"], str(kw["pkg_parent"]), kw["root"].name))
        complete = kw["label"].endswith("head") or kw["root"].name == calls["head_key"]
        return [_row("complete" if complete else "incomplete", [])], 0.0

    monkeypatch.setattr(index_store, "ensure_index", ensure_index)
    monkeypatch.setattr(runner, "compute_side", compute_side)
    monkeypatch.setattr(
        corpus, "load_targets", lambda layout, name, manifest: ([TARGET], "sha")
    )
    monkeypatch.setattr(
        sides, "materialize", lambda layout, git_dir, side: side.pkg_parent
    )
    return calls


def _key(blobs: dict[str, str]) -> str:
    return keys.index_key(
        repo=PIN.name,
        repo_sha=PIN.sha,
        package_blobs=blobs,
        pyproject_blob=None,
        env_fingerprint="env",
    )


def test_an_indexer_change_builds_the_base_index_and_compares_against_it(
    tmp_path: Path, stubs: dict[str, Any]
) -> None:
    head_blobs = {**BLOBS, "cache/indexer.py": "c" * 40}
    stubs["head_key"] = _key(head_blobs)
    base, head = _side("base", BLOBS, "t" * 40), _side("head", head_blobs, "u" * 40)
    run = runner.run_repo(_ctx(tmp_path, base, head), PIN)
    assert run.index_key == _key(head_blobs)
    assert run.base_index_key == _key(BLOBS)
    assert [k for k, _pkg in stubs["indexes"]] == [_key(head_blobs), _key(BLOBS)]
    assert dict(stubs["indexes"])[_key(BLOBS)].replace("\\", "/") == "/pkg/base"
    assert ("rich-base-own-index", "/pkg/base", _key(BLOBS)) in [
        (label, pkg.replace("\\", "/"), root) for label, pkg, root in stubs["sides"]
    ]
    assert run.cross_rows and run.cross_rows[0]["full"]["completeness"] == "incomplete"
    # cached under the base tree and the base index key, so the next run reuses it
    cached = answers.read_answers(
        Layout(tmp_path).baseline(base.tree, _key(BLOBS), PIN.name),
        answers.AnswerKey(base.tree, _key(BLOBS), PIN.name, PIN.sha, run.query_key),
        lambda _m: None,
    )
    assert cached == run.cross_rows


def test_a_query_only_change_needs_no_second_index(
    tmp_path: Path, stubs: dict[str, Any]
) -> None:
    head_blobs = {**BLOBS, "mcp/tools/callers_tool.py": "d" * 40}
    stubs["head_key"] = _key(head_blobs)
    base, head = _side("base", BLOBS, "t" * 40), _side("head", head_blobs, "u" * 40)
    run = runner.run_repo(_ctx(tmp_path, base, head), PIN)
    assert run.base_index_key == run.index_key
    assert run.cross_rows == []
    assert len(stubs["indexes"]) == 1


def _layout_with_gt2(tmp_path: Path) -> tuple[Layout, dict[str, str]]:
    layout = Layout(tmp_path)
    gt2 = {
        "callers": {"a.py::A.f": [["b.py", "g", 10, "bare", 12]]},
        "module_callers": {},
        "defs": [{"key": "a.py::A.f"}],
        "open_sites": {},
    }
    path = layout.gt2("rich")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(gt2), encoding="utf-8")
    return layout, {"gt2/rich.json": corpus.sha256_file(path)}


def test_a_gt2_miss_identical_to_base_on_the_head_index_but_new_on_its_own_is_blamed(
    tmp_path: Path,
) -> None:
    layout, manifest = _layout_with_gt2(tmp_path)
    head = [_row("complete", [])]
    run = runner.RepoRun(
        "rich",
        index_key="k-head",
        base_index_key="k-base",
        base_rows=[_row("complete", [])],  # base code on the head index: identical
        cross_rows=[_row("incomplete", [])],  # base code on its own index
        head_rows=head,
    )
    out = report.judge_repo(layout, Path("py"), run, Policy(), manifest, tmp_path)
    assert [f["kind"] for f in out["truth_failures"]] == ["gt2_miss"]
    assert out["truth_preexisting"] == []
    assert out["comparisons"]["same_index"]["transitions"] == {"complete->complete": 1}
    assert out["comparisons"]["own_index"]["transitions"] == {"incomplete->complete": 1}
    text = report.render({}, [out], report.exit_code([out]))
    assert "base code on its own index" in text
    assert "base code on the head index" in text


def test_with_equal_index_keys_only_one_comparison_is_judged(tmp_path: Path) -> None:
    layout, manifest = _layout_with_gt2(tmp_path)
    run = runner.RepoRun(
        "rich",
        index_key="k",
        base_index_key="k",
        base_rows=[_row("complete", [])],
        head_rows=[_row("complete", [])],
    )
    out = report.judge_repo(layout, Path("py"), run, Policy(), manifest, tmp_path)
    assert list(out["comparisons"]) == ["same_index"]
    assert [f["kind"] for f in out["truth_preexisting"]] == ["gt2_miss"]
    assert out["truth_failures"] == []


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "-qm",
            message,
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.slow_ok  # real git + git archive
def test_snapshots_of_equal_size_trees_extracted_in_one_second_do_not_collide(
    tmp_path: Path,
) -> None:
    from tree_sitter_analyzer.source_fingerprint import source_fingerprint

    repo = tmp_path / "repo"
    pkg = repo / gitutil.PACKAGE
    pkg.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "resolve.py").write_text(
        "def keep(e):\n    return e > 0\n", encoding="utf-8"
    )
    _commit(repo, "base")
    (pkg / "resolve.py").write_text(
        "def keep(e):\n    return e < 0\n", encoding="utf-8"
    )
    _commit(repo, "head")
    base_tree = gitutil.ref_tree(repo, "HEAD~1")
    head_tree = gitutil.ref_tree(repo, "HEAD")
    assert base_tree != head_tree
    time.sleep(1 - (time.time() % 1) + 0.01)  # both extracts inside one second
    gitutil.extract_tree(repo, head_tree, tmp_path / "src" / head_tree)
    gitutil.extract_tree(repo, base_tree, tmp_path / "src" / base_tree)
    fa = source_fingerprint(tmp_path / "src" / base_tree / gitutil.PACKAGE)
    fb = source_fingerprint(tmp_path / "src" / head_tree / gitutil.PACKAGE)
    assert fa != fb
    # deterministic: a re-extract of the same tree gets the same stamps
    again = tmp_path / "again"
    gitutil.extract_tree(repo, base_tree, again)
    assert source_fingerprint(again / gitutil.PACKAGE) == fa


def test_gate_servers_disable_the_query_time_memos(tmp_path: Path) -> None:
    env = mcp_client.server_env(tmp_path, tmp_path / "private")
    assert env["TSA_EVIDENCE_STORE"] == "off"
    tree = tmp_path / "tree"
    (tree / ".ast-cache" / "graph-memo").mkdir(parents=True)
    (tree / ".ast-cache" / "graph-memo" / "x.bin").write_bytes(b"old")
    index_store.block_query_memos(tree)
    blocker = tree / ".ast-cache" / "graph-memo"
    assert blocker.is_file()
    index_store.block_query_memos(tree)  # idempotent
    assert index_store.query_memos_blocked(tree)
    blocker.unlink()
    blocker.mkdir()
    assert not index_store.query_memos_blocked(tree)


def test_the_index_build_runs_in_process_with_one_worker(tmp_path: Path) -> None:
    env = index_store.build_env(tmp_path, tmp_path / "private")
    assert env["TSA_INDEX_WORKERS"] == "1"


def _child() -> None:
    return None


def test_the_index_audit_refuses_a_child_process() -> None:
    with _boot.forbid_child_processes() as started:
        proc = multiprocessing.get_context("spawn").Process(target=_child)
        with pytest.raises(_boot.ChildProcessForbidden):
            proc.start()
    assert started == ["multiprocessing:SpawnProcess"]
    with _boot.forbid_child_processes() as started:
        with pytest.raises(_boot.ChildProcessForbidden):
            subprocess.Popen(["py", "-c", "pass"])  # noqa: S607 - never started
        # a non-Python tool (the indexer runs git) is still allowed
        subprocess.run(["git", "--version"], check=True, capture_output=True)  # noqa: S607
    assert len(started) == 1
    assert multiprocessing.process.BaseProcess.start is not None
    assert subprocess.Popen.__init__.__name__ == "__init__"  # restored
