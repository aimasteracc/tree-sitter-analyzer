"""#1376：test_ast_cache_materialization 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_freezes_private_regular_file(tmp_path: Path) -> None:
    # PR #1253: 破坏性重建输入必须复制到私有不可变叶节点。
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
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
    frozen = materialize_index_candidate_snapshot(snapshot)
    try:
        leaf = Path(frozen.selected_entries[0].frozen_path or "")
        outcome = (
            index_candidate_snapshot_is_materialized(frozen),
            leaf.read_text(encoding="utf-8"),
            leaf.stat().st_mode & 0o777,
        )
    finally:
        cleanup_index_candidate_snapshot(frozen)

    assert outcome == (True, "value = 1\n", 0o600)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_rejects_source_hash_race(tmp_path: Path) -> None:
    # PR #1253: 发现之后发生变化的字节不能授权破坏性清空。
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
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
    source.write_text("value = 2\n", encoding="utf-8")
    frozen = materialize_index_candidate_snapshot(snapshot)

    assert (
        frozen.frozen_root,
        frozen.frozen_error,
        index_candidate_snapshot_is_materialized(frozen),
    ) == (None, "INDEX_CANDIDATE_SOURCE_CHANGED", False)


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.parametrize(
    "tamper",
    [
        "root_mode",
        "max_files",
        "missing_path",
        "leaf_mode",
        "extra_leaf",
        "missing_root",
    ],
)
def test_materialized_candidate_validator_rejects_tampering(
    tmp_path: Path, tamper: str
) -> None:
    # PR #1253: 私有冻结证据必须保留精确的文件系统形状。

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
        index_candidate_snapshot_is_materialized,
        materialize_index_candidate_snapshot,
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
    frozen = materialize_index_candidate_snapshot(snapshot)
    root = Path(frozen.frozen_root or "")
    leaf = Path(frozen.selected_entries[0].frozen_path or "")
    candidate = frozen
    if tamper == "root_mode":
        root.chmod(0o755)
    elif tamper == "max_files":
        candidate = replace(frozen, max_files=0)
    elif tamper == "missing_path":
        candidate = replace(
            frozen, entries=(replace(frozen.selected_entries[0], frozen_path=None),)
        )
    elif tamper == "leaf_mode":
        leaf.chmod(0o644)
    elif tamper == "extra_leaf":
        (root / "extra").write_text("x", encoding="utf-8")
    else:
        cleanup_index_candidate_snapshot(frozen)
    result = index_candidate_snapshot_is_materialized(candidate)
    if tamper != "missing_root":
        cleanup_index_candidate_snapshot(frozen)

    assert result is False


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
@pytest.mark.parametrize(
    "failure",
    ["unsupported", "file_cap", "deadline", "missing_fingerprint", "byte_cap", "hash"],
)
def test_candidate_materialization_reports_fail_closed_reason(
    tmp_path: Path, monkeypatch, failure: str
) -> None:
    # PR #1253: 每个不安全的冻结边界都要返回明确的不完整证据。

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    expected = ""
    if failure == "unsupported":
        monkeypatch.setattr(materialization.os, "name", "nt")
        expected = "SECURE_MATERIALIZATION_UNSUPPORTED"
    elif failure == "file_cap":
        snapshot = replace(snapshot, max_files=0)
        expected = "INDEX_CANDIDATE_MATERIALIZATION_BUDGET"
    elif failure == "deadline":
        from types import SimpleNamespace

        times = iter((0.0, 11.0))
        monkeypatch.setattr(
            materialization, "time", SimpleNamespace(monotonic=lambda: next(times))
        )
        expected = "INDEX_CANDIDATE_MATERIALIZATION_DEADLINE"
    elif failure == "missing_fingerprint":
        snapshot = replace(
            snapshot, entries=(replace(snapshot.selected_entries[0], fingerprint=None),)
        )
        expected = "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"
    elif failure == "byte_cap":
        monkeypatch.setattr(materialization, "_MAX_TOTAL_BYTES", 0)
        expected = "INDEX_CANDIDATE_MATERIALIZATION_BUDGET"
    else:
        fingerprint = replace(
            snapshot.selected_entries[0].fingerprint, content_hash="0" * 64
        )
        snapshot = replace(
            snapshot,
            entries=(replace(snapshot.selected_entries[0], fingerprint=fingerprint),),
        )
        expected = "INDEX_CANDIDATE_SOURCE_CHANGED"

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == expected


def test_materialized_candidate_without_root_identity_is_not_current(tmp_path) -> None:
    # PR #1253 thread 3761703249: 旧版或伪造快照不能授权清空。

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_root_is_current,
    )

    snapshot = SimpleNamespace(project_root=str(tmp_path), root_identity=None)

    assert index_candidate_snapshot_root_is_current(snapshot) is False


def test_materialized_candidate_missing_root_is_not_current(tmp_path) -> None:
    # PR #1253 thread 3761703249: 根目录消失时必须失败关闭。

    from tree_sitter_analyzer.indexing_candidate_materialization import (
        index_candidate_snapshot_root_is_current,
    )

    missing = tmp_path / "missing"
    snapshot = SimpleNamespace(
        project_root=str(missing),
        root_identity=(str(missing.resolve()), 1, 1),
    )

    assert index_candidate_snapshot_root_is_current(snapshot) is False


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_materialized_candidate_rejects_foreign_owner(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: 调用方持有的路径不能冒充进程私有证据。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    frozen = materialization.materialize_index_candidate_snapshot(snapshot)
    real_uid = os.getuid()
    monkeypatch.setattr(materialization.os, "getuid", lambda: real_uid + 1)
    try:
        result = materialization.index_candidate_snapshot_is_materialized(frozen)
    finally:
        materialization.cleanup_index_candidate_snapshot(frozen)

    assert result is False


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_rejects_nonfile_capture(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253: 只有已捕获的普通文件字节可以进入私有 epoch。

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    monkeypatch.setattr(
        materialization,
        "safe_workspace_path",
        lambda *_args, **_kwargs: SimpleNamespace(kind="missing", data=None),
    )

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == "INDEX_CANDIDATE_SOURCE_CHANGED"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_reports_cleanup_failure(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3760428941: 清理不能掩盖主要冻结失败。

    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    snapshot = replace(
        snapshot, entries=(replace(snapshot.selected_entries[0], fingerprint=None),)
    )
    monkeypatch.setattr(
        materialization.os,
        "rmdir",
        lambda *_args: (_ for _ in ()).throw(OSError("cleanup denied")),
    )

    result = materialization.materialize_index_candidate_snapshot(snapshot)

    assert result.frozen_error == "INDEX_CANDIDATE_FROZEN_EVIDENCE_MISSING"


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_chmod_failure_removes_unowned_root(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    roots: list[str] = []
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        roots.append(root)
        return root

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", record_root)
    monkeypatch.setattr(
        materialization.os,
        "chmod",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("chmod denied")),
    )
    result = materialization.materialize_index_candidate_snapshot(snapshot)
    assert result.frozen_error == "chmod denied"
    assert roots and not Path(roots[0]).exists()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_candidate_materialization_fstat_failure_closes_fd_and_root(
    tmp_path: Path, monkeypatch
) -> None:
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    source = tmp_path / "app.py"
    source.write_text("x = 1\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
    )
    opened: list[int] = []
    roots: list[str] = []
    real_open = materialization.os.open
    real_mkdtemp = materialization.tempfile.mkdtemp

    def record_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        roots.append(root)
        return root

    def record_open(*args, **kwargs):
        fd = real_open(*args, **kwargs)
        opened.append(fd)
        return fd

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", record_root)
    monkeypatch.setattr(materialization.os, "open", record_open)
    real_fstat = materialization.os.fstat
    calls = 0

    def fail_first_fstat(fd):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("denied")
        return real_fstat(fd)

    monkeypatch.setattr(materialization.os, "fstat", fail_first_fstat)
    result = materialization.materialize_index_candidate_snapshot(snapshot)
    assert result.frozen_error == "denied"
    assert roots and not Path(roots[0]).exists()
    with pytest.raises(OSError):
        os.fstat(opened[0])
