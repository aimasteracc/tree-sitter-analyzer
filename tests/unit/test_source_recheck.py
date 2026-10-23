"""发布前源码复核：未改动的树不得误报变化，真实变化给出有界差异（#1595）。"""

import time
from types import SimpleNamespace

import pytest

import tree_sitter_analyzer.index_candidate_walker as walker
import tree_sitter_analyzer.indexing_snapshot as snapshots
from tree_sitter_analyzer.cache.generation_indexing import _publication_error
from tree_sitter_analyzer.cache.generation_store import GenerationStore
from tree_sitter_analyzer.cache.source_recheck import (
    MAX_REPORTED_CHANGES,
    SOURCE_CHANGED,
    SOURCE_RECHECK_INCOMPLETE,
    SourceChanged,
    recheck_discovery_seconds,
    source_changed_failure,
)


@pytest.fixture
def store(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    for name in ("a.py", "b.py", "c.py", "d.py"):
        (root / name).write_text(f"def {name[0]}(): return 0\n", encoding="utf-8")
    return GenerationStore(str(root), str(tmp_path / "storage"))


def _slow_discovery(monkeypatch, seconds_per_call):
    """每次读时钟推进固定秒数：模拟构建之后机器负载升高时的复核遍历。"""
    # 从真实时钟起步：POSIX 指纹读取用真实时钟比较同一截止时间。
    clock = {"now": time.monotonic()}

    def monotonic():
        clock["now"] += seconds_per_call
        return clock["now"]

    fake = SimpleNamespace(monotonic=monotonic)
    monkeypatch.setattr(snapshots, "time", fake)
    monkeypatch.setattr(walker, "time", fake)


def _generation_dirs(store):
    return sorted(path.name for path in (store.storage / "generations").iterdir())


def test_loaded_recheck_of_unchanged_tree_publishes(store, monkeypatch):
    # Issue #1595: the publish recheck shared the 5 s discovery budget with the
    # first capture (2,798 entries take 2.6-3.0 s idle on Windows), so a loaded
    # machine turned the budget overrun into INDEX_GENERATION_SOURCE_CHANGED.
    prepared = store.prepare(store.capture())
    _slow_discovery(monkeypatch, 1.0)
    assert store.publish(prepared) == prepared.selector


def test_recheck_budget_overrun_is_incomplete_not_changed(store, monkeypatch):
    # Issue #1595: a recheck that cannot finish is not evidence the source changed.
    prepared = store.prepare(store.capture())
    _slow_discovery(monkeypatch, 100.0)
    with pytest.raises(SourceChanged) as caught:
        store.publish(prepared)
    assert (caught.value.code, caught.value.changes) == (
        SOURCE_RECHECK_INCOMPLETE,
        ("discovery: INDEX_CANDIDATE_DISCOVERY_BUDGET",),
    )


def test_recheck_budget_scales_with_captured_entries(store):
    # Issue #1595: 30 s base + 10 ms per captured entry (measured ~1 ms/entry).
    snapshot = store._snapshot()
    assert (snapshot.discovered, recheck_discovery_seconds(snapshot)) == (4, 30.04)


def test_real_change_lists_modified_and_added_paths(store):
    # Issue #1595: a real change still blocks publication and names the paths.
    first = store.sync()
    prepared = store.prepare(store.capture())
    (store.root / "a.py").write_text("def a(): return 12345\n", encoding="utf-8")
    (store.root / "e.py").write_text("def e(): return 0\n", encoding="utf-8")
    with pytest.raises(SourceChanged) as caught:
        store.publish(prepared)
    assert (caught.value.code, caught.value.changes, store.active_selector()) == (
        SOURCE_CHANGED,
        ("added: e.py", "modified: a.py"),
        first,
    )


def test_removed_path_is_listed(store):
    # Issue #1595: a deleted candidate file is reported as removed.
    prepared = store.prepare(store.capture())
    (store.root / "d.py").unlink()
    with pytest.raises(SourceChanged) as caught:
        store.publish(prepared)
    assert caught.value.changes == ("removed: d.py",)


def test_change_list_is_bounded(store):
    # Issue #1595: the reported list is capped; the total stays exact.
    prepared = store.prepare(store.capture())
    for index in range(MAX_REPORTED_CHANGES + 5):
        (store.root / f"n{index:02}.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(SourceChanged) as caught:
        store.publish(prepared)
    assert (len(caught.value.changes), caught.value.total, caught.value.changes[0]) == (
        MAX_REPORTED_CHANGES,
        MAX_REPORTED_CHANGES + 5,
        "added: n00.py",
    )


def test_failed_publication_leaves_no_orphan_generation(store):
    # Issue #1595: a sealed failed build survived #1567 retirement as the newest
    # retained generation (336 MB measured); it must be removed at once.
    first = store.sync()
    prepared = store.prepare(store.capture())
    (store.root / "a.py").write_text("def a(): return 12345\n", encoding="utf-8")
    with pytest.raises(SourceChanged):
        store.publish(prepared)
    assert _generation_dirs(store) == [first.generation_id]


def test_failed_prepare_leaves_no_orphan_generation(store, monkeypatch):
    # Issue #1595: a build that fails before sealing is removed, not left pinned.
    from tree_sitter_analyzer.incremental_sync import IncrementalSync

    def broken(*_args, **_kwargs):
        raise RuntimeError("build failed")

    monkeypatch.setattr(IncrementalSync, "sync", broken)
    with pytest.raises(RuntimeError, match="^build failed$"):
        store.prepare(store.capture())
    assert _generation_dirs(store) == []


def test_typed_failure_tells_the_caller_to_retry():
    # Issue #1595: the reply is typed and retryable, not error_type=internal.
    failure = source_changed_failure(SourceChanged(SOURCE_CHANGED, ["modified: a.py"]))
    next_step = (
        "Nothing was published and the previous index is still active: 1 source "
        "path(s) changed while the index was built. Retry the same index call; if "
        "it keeps failing, stop the process that is modifying the listed files or "
        "exclude them with exclude_patterns."
    )
    # RFC-0032 slice 4：error_code 是准入码，原因码保留在 error 与 cause_code。
    assert failure == {
        "success": False,
        "verdict": "ERROR",
        "published": False,
        "error_code": "INDEX_CANDIDATE_SUPERSEDED",
        "cause_code": "INDEX_GENERATION_SOURCE_CHANGED",
        "error": "INDEX_GENERATION_SOURCE_CHANGED",
        "retryable": True,
        "retry_after_ms": 5000,
        "next_action": "recapture",
        "changes": ["modified: a.py"],
        "changes_total": 1,
        "changes_truncated": False,
        "next_step": next_step,
        "summary_line": "index not published: INDEX_GENERATION_SOURCE_CHANGED "
        "(1 change(s))",
        "agent_summary": {
            "verdict": "ERROR",
            "summary_line": "index not published: INDEX_GENERATION_SOURCE_CHANGED "
            "(1 change(s))",
            "next_step": next_step,
        },
    }


def test_full_index_publication_error_carries_source_changed_code():
    # Issue #1595: index action=full reports the same typed fields as action=cache.
    failure = _publication_error(
        SourceChanged(SOURCE_RECHECK_INCOMPLETE, ["discovery: X"]),
        "/repo",
        "generation_publication",
    )
    assert (
        failure["error_code"],
        failure["retryable"],
        failure["changes"],
        failure["next_step"],
    ) == (
        "INDEX_GENERATION_SOURCE_RECHECK_INCOMPLETE",
        True,
        ["discovery: X"],
        "Nothing was published and the previous index is still active: the "
        "pre-publish source recheck could not finish. Retry the same index call; "
        "if it keeps failing, stop the process that is modifying the listed files "
        "or exclude them with exclude_patterns.",
    )
