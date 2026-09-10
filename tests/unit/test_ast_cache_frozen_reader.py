"""#1376：test_ast_cache_frozen_reader 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _python_language, _snapshot, requires_posix_fd
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.indexing_snapshot import (
    IndexFileFingerprint,
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


class TestAstExtractionWorker:
    def test_init_worker_parser_sets_reusable_parser(self):
        import tree_sitter_analyzer.cache.extraction as extraction

        extraction._worker_parser = None

        extraction._init_worker_parser()

        assert extraction._worker_parser is not None
        assert hasattr(extraction._worker_parser, "parse_file")


@requires_posix_fd
def test_frozen_candidate_reader_rejects_non_regular_leaf(tmp_path):
    # PR #1253 thread 3759852177: worker 只接受私有普通文件的字节。
    from tree_sitter_analyzer.cache.extraction import _read_frozen_candidate

    directory = tmp_path / "candidate"
    directory.mkdir()
    with pytest.raises(OSError, match="invalid frozen candidate"):
        _read_frozen_candidate(str(directory))


@requires_posix_fd
def test_frozen_candidate_reader_rejects_growth_past_limit(tmp_path, monkeypatch):
    # PR #1253 thread 3759852177: 增长中的冻结叶节点仍须受限。
    from tree_sitter_analyzer.cache import extraction

    candidate = tmp_path / "candidate"
    candidate.write_bytes(b"12345")
    real_fstat = extraction.os.fstat

    def admitted_size(fd):
        info = real_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_size=4)

    monkeypatch.setattr(extraction, "_MAX_FROZEN_FILE_BYTES", 4)
    monkeypatch.setattr(extraction.os, "fstat", admitted_size)
    with pytest.raises(OSError, match="exceeds byte limit"):
        extraction._read_frozen_candidate(str(candidate))


@pytest.mark.parametrize("missing", ["fingerprint", "identity"])
def test_index_file_rejects_incomplete_frozen_evidence(tmp_path, missing):
    # PR #1253: 冻结源码路径必须具有两个捕获证据字段。
    logical = tmp_path / "app.py"
    frozen = tmp_path / "frozen"
    frozen.write_text("value = 1\n", encoding="utf-8")
    fingerprint = IndexFileFingerprint(0, 0, 10)
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_file(
            str(logical),
            language="python",
            _source_path=str(frozen),
            _source_fingerprint=None if missing == "fingerprint" else fingerprint,
            _frozen_identity=None if missing == "identity" else (0, 0, 0),
        )
    finally:
        cache.close()

    assert (result["status"], result["reason"]) == (
        "error",
        "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING",
    )


def test_index_file_reports_unavailable_frozen_evidence(tmp_path, monkeypatch):
    # PR #1253: 冻结源码消失后必须在解析之前失败关闭。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    logical = tmp_path / "app.py"
    fingerprint = IndexFileFingerprint(0, 0, 10)
    monkeypatch.setattr(
        materialization,
        "read_frozen_candidate",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("frozen evidence unavailable")
        ),
    )
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_file(
            str(logical),
            language="python",
            _source_path=str(tmp_path / "missing"),
            _source_fingerprint=fingerprint,
            _frozen_identity=(0, 0, 0),
        )
    finally:
        cache.close()

    assert (result["status"], result["reason"]) == (
        "error",
        "frozen evidence unavailable",
    )


@requires_posix_fd
def test_frozen_worker_requires_captured_fingerprint(tmp_path):
    # PR #1253 thread 3759852177: 仅有冻结路径名不构成证据。
    from tree_sitter_analyzer.cache.extraction import _worker_index_file

    logical = tmp_path / "app.py"
    frozen = tmp_path / "candidate"
    frozen.write_text("value = 1\n", encoding="utf-8")
    result = _worker_index_file(
        (str(logical), str(tmp_path), "python", None, str(frozen))
    )
    assert (result["status"], result["reason"]) == (
        "io_error",
        "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING",
    )


@requires_posix_fd
def test_frozen_worker_rejects_bytes_outside_captured_epoch(tmp_path):
    # PR #1253 thread 3759852177: worker 字节必须始终绑定捕获内容。
    from tree_sitter_analyzer.cache.extraction import _worker_index_file

    logical = tmp_path / "app.py"
    logical.write_text("value = 1\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path, logical)
    fingerprint = snapshot.selected_entries[0].fingerprint
    assert fingerprint is not None
    frozen = tmp_path / "candidate"
    frozen.write_text("value = 2\n", encoding="utf-8")
    result = _worker_index_file(
        (str(logical), str(tmp_path), "python", fingerprint, str(frozen))
    )
    assert (result["status"], result["reason"]) == (
        "source_changed",
        "file changed after candidate snapshot",
    )


@requires_posix_fd
def test_frozen_worker_rejects_fifo_replacement_without_blocking(tmp_path):
    # PR #1253 thread 3760428948: O_NONBLOCK 必须立即拒绝被替换的 FIFO。
    from tree_sitter_analyzer.cache.extraction import _worker_index_file
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    logical = tmp_path / "app.py"
    logical.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(logical),),
        language_fn=_python_language,
        materialize=True,
    )
    entry = snapshot.selected_entries[0]
    assert entry.frozen_path is not None
    os.unlink(entry.frozen_path)
    os.mkfifo(entry.frozen_path)
    try:
        result = _worker_index_file(
            (
                str(logical),
                str(tmp_path),
                "python",
                entry.fingerprint,
                entry.frozen_path,
                entry.frozen_identity,
                snapshot.frozen_read_deadline,
            )
        )
    finally:
        cleanup_index_candidate_snapshot(snapshot)

    assert (result["status"], result["reason"]) == (
        "source_changed",
        "file changed after candidate snapshot",
    )


@requires_posix_fd
def test_frozen_worker_rejects_expired_absolute_deadline(tmp_path):
    # PR #1253 thread 3760428948: worker 读取继承快照的绝对截止时间。
    from tree_sitter_analyzer.cache.extraction import _worker_index_file
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    logical = tmp_path / "app.py"
    logical.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(logical),),
        language_fn=_python_language,
        materialize=True,
    )
    entry = snapshot.selected_entries[0]
    try:
        result = _worker_index_file(
            (
                str(logical),
                str(tmp_path),
                "python",
                entry.fingerprint,
                entry.frozen_path,
                entry.frozen_identity,
                time.monotonic() - 1.0,
            )
        )
    finally:
        cleanup_index_candidate_snapshot(snapshot)

    assert (result["status"], result["reason"]) == (
        "source_changed",
        "file changed after candidate snapshot",
    )


@requires_posix_fd
def test_force_rebuild_later_frozen_worker_gets_fresh_read_deadline(
    tmp_path, monkeypatch
):
    # PR #1253 thread 3760944067: 构建耗时不能使不可变输入过期。
    import tree_sitter_analyzer.cache.indexer as indexer
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization
    from tree_sitter_analyzer.cache.extraction import _worker_index_file
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    first = tmp_path / "first.py"
    later = tmp_path / "later.py"
    first.write_text("first = 1\n", encoding="utf-8")
    later.write_text("later = 2\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(first), str(later)),
        language_fn=_python_language,
        materialize=True,
    )
    assert snapshot.frozen_read_deadline is not None
    observed_deadlines = []

    def delayed_parallel(
        cache,
        candidates,
        workers,
        fingerprints,
        frozen_paths,
        frozen_identities,
        frozen_deadline,
    ):
        observed_deadlines.append(frozen_deadline)
        advanced = snapshot.frozen_read_deadline + 1.0
        monkeypatch.setattr(
            materialization, "time", SimpleNamespace(monotonic=lambda: advanced)
        )
        return [
            _worker_index_file(
                (
                    path,
                    cache.project_root,
                    language,
                    fingerprints[path],
                    frozen_paths[path],
                    frozen_identities[path],
                    frozen_deadline,
                )
            )
            for path, language in candidates
        ]

    monkeypatch.setattr(indexer, "index_parallel", delayed_parallel)
    cache = ASTCache(str(tmp_path))
    try:
        result = cache.index_project(
            max_files=10, force=True, workers=2, candidate_snapshot=snapshot
        )
    finally:
        cache.close()
        cleanup_index_candidate_snapshot(snapshot)

    assert (result["indexed"], result["errors"], observed_deadlines) == (2, 0, [None])


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_rejects_original_size_mismatch(tmp_path: Path) -> None:
    # PR #1253 thread 3760428948: 原始字节大小是重放授权的一部分。
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        read_frozen_candidate,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    fingerprint = snapshot.selected_entries[0].fingerprint
    if fingerprint is None:
        pytest.fail("selected source fingerprint was not captured")
    source.write_text("x", encoding="utf-8")

    with pytest.raises(OSError, match="source size changed"):
        read_frozen_candidate(str(source), expected=fingerprint)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_checks_deadline_before_each_read(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428948: 时钟到期后，应在下一次读取前停止重放。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "candidate"
    source.write_bytes(b"x")
    from types import SimpleNamespace

    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(
        materialization, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    with pytest.raises(OSError, match="read deadline exceeded"):
        materialization.read_frozen_candidate(str(source), deadline=1.0)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_certified_frozen_reader_checks_deadline_after_each_read(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428948: 停滞的读取不能发布逾期字节。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "candidate"
    source.write_bytes(b"x")
    from types import SimpleNamespace

    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(
        materialization, "time", SimpleNamespace(monotonic=lambda: next(ticks))
    )

    with pytest.raises(OSError, match="read deadline exceeded"):
        materialization.read_frozen_candidate(str(source), deadline=1.0)


def test_parse_and_write_returns_exact_parser_failure():
    # PR #1253: 解析失败不能进入任何索引 writer 事务。
    from types import SimpleNamespace

    from tree_sitter_analyzer.cache.indexer import parse_and_write

    cache = SimpleNamespace(
        parser=SimpleNamespace(
            parse_code=lambda *_args, **_kwargs: SimpleNamespace(
                success=False, error_message="invalid source"
            )
        )
    )

    result = parse_and_write(
        cache,
        None,
        "/project/bad.py",
        "bad.py",
        "python",
        None,
        "bad source",
        "hash",
        14,
    )

    assert result == {
        "file": "bad.py",
        "status": "error",
        "reason": "invalid source",
    }


def test_index_file_preserved_metadata_uses_current_source(tmp_path):
    """单文件入口不能用相同元数据复用旧源码或旧语法树。"""
    # 2026-09-08 实测：等长等 mtime 保存曾复用旧索引和旧语法树。
    path = tmp_path / "app.py"
    path.write_text("def old(): return 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(path))["status"] == "indexed"
        before = path.stat()
        path.write_text("def new(): return 2\n", encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert cache.index_file(str(path))["status"] == "indexed"
        names = cache.get_conn().execute("SELECT name FROM ast_symbol_rows").fetchall()
        assert [row[0] for row in names] == ["new"]
        assert cache.index_file(str(path))["status"] == "cached"
    finally:
        cache.close()


def test_index_file_preserves_cp1252_identifiers(tmp_path):
    """#1405：编码检测后的源码同时用于摘要和语法树，不能丢失重音字符。"""
    path = tmp_path / "app.py"
    path.write_bytes("# coding: cp1252\ndef café(): return 1\n".encode("cp1252"))
    cache = ASTCache(str(tmp_path))
    try:
        assert cache.index_file(str(path))["status"] == "indexed"
        assert [
            r[0] for r in cache.get_conn().execute("SELECT name FROM ast_symbol_rows")
        ] == ["café"]
        assert cache.index_file(str(path))["status"] == "cached"
    finally:
        cache.close()


def test_portable_worker_preserves_cp1252_identifiers(tmp_path, monkeypatch):
    """#1405：便携工作进程必须保留与串行入口一致的编码语义。"""
    import tree_sitter_analyzer.cache.extraction as owner

    path = tmp_path / "app.py"
    path.write_bytes("# coding: cp1252\ndef café(): return 1\n".encode("cp1252"))
    monkeypatch.setattr(
        owner, "os", SimpleNamespace(name="nt", path=os.path, stat=os.stat)
    )
    result = owner._worker_index_file((str(path), str(tmp_path), "python"))
    assert result["status"] == "ok"
    assert [row[0] for row in result["symbol_rows"]] == ["café"]
