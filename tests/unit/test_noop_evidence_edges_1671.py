"""#1671：收敛刷新记录与建库前零变化判定的失败闭合分支。

每个畸形输入、缺失表、版本不符或读取失败都必须让判定返回“不能证明未变”
（``None`` / ``False``），从而退回真实的建库与发布路径。
"""

from __future__ import annotations

import json
import os
import sqlite3
from types import SimpleNamespace

import pytest

from tree_sitter_analyzer.cache import generation_noop_precheck as precheck
from tree_sitter_analyzer.cache import stable_failures as sf
from tree_sitter_analyzer.indexing_snapshot import (
    IndexFileFingerprint,
    IndexSnapshotEntry,
)

_HASH = "a" * 64
_STABLE = {"failure_kind": "stable"}


def _failure(file="x.swift", reason="no grammar", content_hash=_HASH, **extra):
    return {
        "file": file,
        "status": "error",
        "reason": reason,
        "content_hash": content_hash,
        **_STABLE,
        **extra,
    }


def test_failures_from_details_accepts_only_complete_stable_failures() -> None:
    good = _failure()
    assert sf.failures_from_details([good, "noise", {"status": "cached"}], 1) == (
        sf.StableFailure("x.swift", _HASH, "no grammar"),
    )
    assert (
        sf.failures_from_details([], 0),
        sf.failures_from_details([{**good, "failure_kind": "transient"}], 1),
        sf.failures_from_details([{**good, "content_hash": "short"}], 1),
        sf.failures_from_details([{**good, "file": ""}], 1),
        sf.failures_from_details([{**good, "reason": None}], 1),
        sf.failures_from_details([good, good], 2),
        sf.failures_from_details([good], 2),
    ) == ((), None, None, None, None, None, None)


def _encoded(**overrides) -> str:
    data = {
        "version": sf.RECORD_VERSION,
        "root": "/r",
        "scope": "{}",
        "extractor_version": 40,
        "pipeline_version": 2,
        "failures": [["x.swift", _HASH, "no grammar"]],
        **overrides,
    }
    return json.dumps(data)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "HUGE",
        "{not json",
        json.dumps([1]),
        _encoded(version=99),
        _encoded(root=1),
        _encoded(extractor_version="40"),
        _encoded(failures="x"),
        _encoded(failures=[["x.swift", _HASH]]),
        _encoded(failures=[["", _HASH, "r"]]),
        _encoded(failures=[["x.swift", "bad", "r"]]),
        _encoded(failures=[["a", _HASH, "r"], ["a", _HASH, "r"]]),
    ],
)
def test_malformed_records_are_rejected(value) -> None:
    if value == "HUGE":  # 参数本身不能太大（会进入 PYTEST_CURRENT_TEST 环境变量）
        value = "x" * (2 * 1024 * 1024)
    assert sf._decode(value) is None


def test_record_roundtrip_and_missing_table() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        assert sf.read_record(conn) is None
        assert (
            sf.issue_record(
                conn,
                project_root="/r",
                scope="{}",
                extractor_version=40,
                failures=(),
            )
            is False
        )
        conn.execute(
            "CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        failure = sf.StableFailure("x.swift", _HASH, "no grammar")
        assert sf.issue_record(
            conn,
            project_root=".",
            scope="{}",
            extractor_version=40,
            failures=(failure,),
        )
        record = sf.read_record(conn)
        assert (record.failures, record.by_file()) == (
            (failure,),
            {"x.swift": failure},
        )
        sf.clear_record(conn)
        assert sf.read_record(conn) is None
    finally:
        conn.close()
    closed = sqlite3.connect(":memory:")
    closed.close()
    assert sf.read_record(closed) is None


def test_oversized_record_is_not_issued(monkeypatch) -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        monkeypatch.setattr(sf, "_RECORD_BYTE_LIMIT", 10)
        assert (
            sf.issue_record(
                conn, project_root=".", scope="{}", extractor_version=40, failures=()
            ),
            sf.read_record(conn),
        ) == (False, None)
    finally:
        conn.close()


def _candidate(paths, **overrides):
    entries = [SimpleNamespace(rel_path=path, decision="selected") for path in paths]
    values = {
        "errors": 0,
        "discovery_error": None,
        "truncated_by_max_files": False,
        "discovery_reconciled": True,
        "selected_entries": entries,
        **overrides,
    }
    return SimpleNamespace(**values)


def _index_db(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ast_index (file_path TEXT)")
    conn.execute("CREATE TABLE ast_cache_metadata (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO ast_index VALUES (?)", [(r,) for r in rows])
    return conn


def test_issue_after_run_checks_rows_and_failures() -> None:
    kwargs = {
        "project_root": ".",
        "scope": "{}",
        "extractor_version": 40,
        "converged": True,
    }
    conn = _index_db(["a.py"])
    try:
        assert (
            # 失败文件不在选中集合中
            sf.issue_after_run(
                conn,
                candidate=_candidate(["a.py"]),
                details=[_failure("z.swift")],
                errors=1,
                stamped=False,
                **kwargs,
            ),
            # 行集合不等于“选中减失败”
            sf.issue_after_run(
                conn,
                candidate=_candidate(["a.py", "b.py", "x.swift"]),
                details=[_failure()],
                errors=1,
                stamped=False,
                **kwargs,
            ),
            # 无失败却未盖清单
            sf.issue_after_run(
                conn,
                candidate=_candidate(["a.py"]),
                details=[],
                errors=0,
                stamped=False,
                **kwargs,
            ),
            # 候选不精确
            sf.issue_after_run(
                conn,
                candidate=_candidate(["a.py"], errors=1),
                details=[],
                errors=0,
                stamped=True,
                **kwargs,
            ),
        ) == (False, False, False, False)
    finally:
        conn.close()


def test_issue_after_run_rolls_back_a_failed_write(monkeypatch) -> None:
    conn = _index_db(["a.py"])

    def broken(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sf, "issue_record", broken)
    try:
        assert (
            sf.issue_after_run(
                conn,
                project_root=".",
                candidate=_candidate(["a.py"]),
                scope="{}",
                extractor_version=40,
                details=[],
                errors=0,
                converged=True,
                stamped=True,
            )
            is False
        )
    finally:
        conn.close()


def test_issue_after_stamp_requires_scope_and_current_marker() -> None:
    conn = _index_db(["a.py"])
    try:
        assert (
            sf.issue_after_stamp(conn, ".", _candidate(["a.py"]), None),
            sf.issue_after_stamp(conn, ".", _candidate(["a.py"]), object()),
        ) == (False, False)
    finally:
        conn.close()


def _entry(path, *, content_hash="", language="python", size=None, mtime=None):
    info = os.stat(path)
    fingerprint = IndexFileFingerprint(
        mtime_ns=info.st_mtime_ns if mtime is None else mtime,
        ctime_ns=info.st_ctime_ns,
        file_size=info.st_size if size is None else size,
        content_hash=content_hash,
    )
    return IndexSnapshotEntry(
        str(path), path.name, language, "selected", fingerprint=fingerprint
    )


def test_bound_source_is_rejected_when_metadata_differs(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    entry = _entry(path)

    assert (
        precheck._read_bound_source(entry),
        precheck._read_bound_source(_entry(path, size=999)),
        precheck._read_bound_source(
            IndexSnapshotEntry(str(path), "a.py", "python", "selected")
        ),
    ) == ("x = 1\n", None, None)
    path.unlink()
    assert precheck._read_bound_source(entry) is None


def test_content_hash_sources(tmp_path) -> None:
    from tree_sitter_analyzer.index_source_stream import _UNREADABLE_PREFIX
    from tree_sitter_analyzer.indexing_snapshot import index_source_content_hash

    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    entry = _entry(path)

    assert (
        precheck._content_hash(entry),
        precheck._content_hash(entry, {"a.py": "b" * 64}),
        precheck._content_hash(entry, {"a.py": _UNREADABLE_PREFIX + "locked"}),
        precheck._content_hash(_entry(path, content_hash="<unsafe>")),
        precheck._content_hash(
            IndexSnapshotEntry(str(path), "a.py", "python", "selected")
        ),
    ) == (index_source_content_hash("x = 1\n"), "b" * 64, None, None, None)


def test_bound_digests_skips_malformed_items() -> None:
    candidate = SimpleNamespace(
        source_contents=(
            ("a.py", (_HASH, ())),
            ("b.py", None),
            ("c.py", ("", ())),
            ("bad",),
            (1, (_HASH, ())),
        )
    )
    assert precheck.bound_digests(candidate) == {"a.py": _HASH}


def test_same_failure_needs_the_same_bytes_and_a_language(tmp_path) -> None:
    path = tmp_path / "a.swift"
    path.write_text("func f() {}\n", encoding="utf-8")
    failure = sf.StableFailure("a.swift", _HASH, "no grammar")

    assert (
        precheck._same_failure(_entry(path, language="swift"), failure),
        precheck._same_failure(_entry(path, language=None), failure),
    ) == (False, False)


def test_schema_and_rows_must_be_current() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE TABLE ast_schema_version (version INTEGER)")
        conn.execute("INSERT INTO ast_schema_version VALUES (1)")
        conn.execute(
            "CREATE TABLE ast_index (file_path TEXT, content_hash TEXT, mtime_ns INT, "
            "file_size INT, extractor_version INT, certified_at INT)"
        )
        conn.execute("INSERT INTO ast_index VALUES ('a.py', ?, 1, 2, 39, 1)", (_HASH,))
        old_version = precheck._indexed_rows(conn, 40)
        conn.execute("UPDATE ast_index SET extractor_version = 40, certified_at = NULL")
        uncertified = precheck._indexed_rows(conn, 40)
        assert (precheck._schema_is_current(conn), old_version, uncertified) == (
            False,
            None,
            None,
        )
    finally:
        conn.close()


def test_unchanged_before_build_fails_closed(tmp_path, monkeypatch) -> None:
    exact = _candidate([])
    no_parent = SimpleNamespace(parent=None, snapshot=exact)
    parent = SimpleNamespace(generation_id="0" * 32)
    store = SimpleNamespace(storage=tmp_path)

    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.generation_pins.pin_generation",
        lambda *_a: None,
    )
    retiring = precheck.unchanged_before_build(
        store, SimpleNamespace(parent=parent, snapshot=exact)
    )

    def refuse(*_a):
        raise OSError("pin directory unwritable")

    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.generation_pins.pin_generation", refuse
    )
    unpinnable = precheck.unchanged_before_build(
        store, SimpleNamespace(parent=parent, snapshot=exact)
    )
    inexact = precheck.unchanged_before_build(
        store, SimpleNamespace(parent=parent, snapshot=_candidate([], errors=1))
    )

    assert (
        precheck.unchanged_before_build(store, no_parent),
        retiring,
        unpinnable,
        inexact,
    ) == (None, None, None, None)


def test_unreadable_parent_database_fails_closed(tmp_path, monkeypatch) -> None:
    released: list[bool] = []
    pin = SimpleNamespace(release=lambda: released.append(True))
    monkeypatch.setattr(
        "tree_sitter_analyzer.cache.generation_pins.pin_generation",
        lambda *_a: pin,
    )
    store = SimpleNamespace(
        storage=tmp_path,
        root=tmp_path,
        scope=None,
        database=lambda _s: tmp_path / "missing" / "index.db",
    )
    candidate = SimpleNamespace(
        parent=SimpleNamespace(generation_id="0" * 32), snapshot=_candidate([])
    )

    assert (precheck.unchanged_before_build(store, candidate), released) == (
        None,
        [True],
    )


def test_sync_publication_is_reported_only_on_sync_results() -> None:
    from tree_sitter_analyzer.cache.generation_indexing import _report_sync_publication
    from tree_sitter_analyzer.incremental_sync_support import SyncResult

    other = SimpleNamespace()
    result = SyncResult()
    _report_sync_publication(other, False, "INDEX_NOT_PUBLISHABLE")
    _report_sync_publication(result, False, "INDEX_NOT_PUBLISHABLE")

    assert (
        vars(other),
        result.to_dict()["published"],
        result.to_dict()["publication_reason"],
    ) == ({}, False, "INDEX_NOT_PUBLISHABLE")


def test_unchanged_sync_reports_stable_failures_to_the_callback(tmp_path, monkeypatch):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    (tmp_path / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (tmp_path / "broken.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message="no grammar")
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    scope = make_source_scope_descriptor()
    seen: list[dict] = []

    def sync(callback=None):
        cache = ASTCache(str(tmp_path))
        try:
            return IncrementalSync(cache).sync(
                max_files=scope.certification_max_files,
                exclude_patterns=scope.effective_excludes,
                source_scope=scope,
                callback=callback,
            )
        finally:
            cache.close()

    sync()
    result = sync(seen.append)

    assert (
        result.publication_reason,
        result.unchanged_files,
        [(d["file"], d["reason"], d["status"]) for d in seen],
    ) == ("INDEX_UNCHANGED", 1, [("broken.py", "no grammar", "error")])
