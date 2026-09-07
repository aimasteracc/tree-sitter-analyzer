"""#1376：test_ast_cache_scope_partition 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
import sqlite3
from pathlib import Path

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import _CacheRoot, _OsProxy
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.cache.indexer import (
    walk_and_partition,
)
from tree_sitter_analyzer.index_candidate_walker import walk_candidate_entries
from tree_sitter_analyzer.index_snapshot_schema import stamp_full_index_manifest
from tree_sitter_analyzer.indexing_snapshot import (
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


def test_language_scoped_partition_marks_other_language_skip_incomplete(
    tmp_path: Path,
) -> None:
    source = tmp_path / "client.js"
    source.write_text("const answer = 42;\n", encoding="utf-8")
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        language_filter="python",
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "javascript",
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE ast_index (file_path TEXT PRIMARY KEY, content_hash TEXT, "
        "mtime_ns INTEGER, file_size INTEGER, extractor_version INTEGER)"
    )

    stats, candidates, count = walk_and_partition(
        _CacheRoot(str(tmp_path)),
        conn,
        max_files=10,
        force=False,
        activation_enabled=False,
        walk_fn=lambda _root: (),
        language_fn=lambda _path: None,
        extractor_version=1,
        make_error_entry=lambda path, reason: {"file": path, "reason": reason},
        language_filter="python",
        candidate_snapshot=snapshot,
    )

    assert (stats["skipped"], stats["incomplete_skips"], candidates, count) == (
        1,
        1,
        [],
        1,
    )
    conn.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253: authoritative manifest")
def test_force_with_root_scandir_error_preserves_every_persisted_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # GH-1253：不完整的发现结果不能授权破坏性的 force clear。
    source = tmp_path / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    tables = (
        "ast_index",
        "ast_symbol_rows",
        "edges",
        "ast_index_snapshot_manifest",
    )

    def persisted_rows() -> dict[str, list[tuple[object, ...]]]:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }

    before = persisted_rows()

    def fail_root_scandir(_root_fd):
        raise OSError("root enumeration denied")

    monkeypatch.setattr(os, "scandir", fail_root_scandir)
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda root: walk_candidate_entries(
            root,
            excluded_dir_names=frozenset(),
            entry_budget=10,
            path_byte_budget=10_000,
            discovery_seconds=10.0,
            budget_error="INDEX_CANDIDATE_DISCOVERY_BUDGET",
        ),
        language_fn=lambda path: "python" if path.endswith(".py") else None,
    )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    assert (snapshot.errors, snapshot.discovery_error) == (
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert (result["verdict"], result["errors"], result["indexed"]) == (
        "WARN",
        1,
        0,
    )
    assert persisted_rows() == before
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_force_with_renamed_directory_swap_preserves_persisted_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # PR #1253 thread 3758928326: 普通目录被替换时应视为发现不完整。
    import tree_sitter_analyzer.index_candidate_walker as walker

    package = tmp_path / "pkg"
    package.mkdir()
    source = package / "app.py"
    source.write_text("def answer():\n    return 42\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    stamp_full_index_manifest(cache.get_conn(), str(tmp_path))
    conn = cache.get_conn()
    tables = (
        "ast_index",
        "ast_symbol_rows",
        "edges",
        "ast_index_snapshot_manifest",
    )

    def persisted_rows() -> dict[str, list[tuple[object, ...]]]:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table}")]
            for table in tables
        }

    before = persisted_rows()
    real_open = walker.os.open
    swapped = False

    def swap_before_child_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
            swapped = True
            package.rename(tmp_path / "original-pkg")
            package.mkdir()
        return real_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(walker.os, "open", swap_before_child_open)
        snapshot = build_index_candidate_snapshot(
            str(tmp_path),
            max_files=10,
            exclude_patterns=frozenset(),
            walk_fn=lambda root: walk_candidate_entries(
                root,
                excluded_dir_names=frozenset(),
                entry_budget=10,
                path_byte_budget=10_000,
                discovery_seconds=10.0,
                budget_error="INDEX_CANDIDATE_DISCOVERY_BUDGET",
            ),
            language_fn=lambda path: "python" if path.endswith(".py") else None,
        )

    result = cache.index_project(
        max_files=10,
        force=True,
        exclude_patterns=frozenset(),
        candidate_snapshot=snapshot,
    )

    assert (swapped, snapshot.errors, snapshot.discovery_error) == (
        True,
        1,
        "INDEX_CANDIDATE_DISCOVERY_ERROR",
    )
    assert (result["verdict"], result["errors"], result["indexed"]) == (
        "WARN",
        1,
        0,
    )
    assert persisted_rows() == before
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_owned_truncated_force_materialization_is_cleaned_before_abort(
    tmp_path: Path, monkeypatch
) -> None:
    # PR #1253 thread 3759852177: 授权失败时清理私有字节。
    import tree_sitter_analyzer.indexing_candidate_materialization as materialization

    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    created: list[str] = []
    real_mkdtemp = materialization.tempfile.mkdtemp

    def remember_root(*args, **kwargs):
        root = real_mkdtemp(*args, **kwargs)
        created.append(root)
        return root

    monkeypatch.setattr(materialization.tempfile, "mkdtemp", remember_root)
    result = cache.index_project(max_files=1, force=True)

    assert (result["verdict"], len(created), os.path.exists(created[0])) == (
        "WARN",
        1,
        False,
    )
    cache.close()


@pytest.mark.skipif(os.name != "posix", reason="GH-1253")
def test_force_preflight_hash_change_preserves_existing_rows(tmp_path: Path) -> None:
    # PR #1253 thread 3760428948: 每个冻结叶节点都必须在 force clear 前计算哈希。
    from tree_sitter_analyzer.indexing_candidate_materialization import (
        cleanup_index_candidate_snapshot,
    )

    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(source))
    before = [tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")]
    snapshot = build_index_candidate_snapshot(
        str(tmp_path),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda _root: (str(source),),
        language_fn=lambda _path: "python",
        materialize=True,
    )
    frozen_path = Path(snapshot.selected_entries[0].frozen_path or "")
    frozen_path.write_text("value = 2\n", encoding="utf-8")
    try:
        result = cache.index_project(
            max_files=10,
            force=True,
            workers=0,
            exclude_patterns=frozenset(),
            candidate_snapshot=snapshot,
        )
        after = [
            tuple(row) for row in cache.get_conn().execute("SELECT * FROM ast_index")
        ]
    finally:
        cleanup_index_candidate_snapshot(snapshot)
        cache.close()

    assert (result["verdict"], result["indexed"], after) == ("WARN", 0, before)


def test_candidate_less_windows_scope_restores_only_operational_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: Windows 保留旧版调用图可用性，但独立的
    # 权威 manifest 在缺少描述符快照时仍不受支持。
    import tree_sitter_analyzer.cache.indexer as indexer

    (tmp_path / "app.py").write_text("def app(): pass\n", encoding="utf-8")
    monkeypatch.setattr(indexer, "os", _OsProxy(name="nt"))
    monkeypatch.setattr(
        indexer,
        "walk_index_candidate_entries",
        lambda *_args, **_kwargs: pytest.fail("secure candidate walk attempted"),
    )

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result == {"app.py"}


def test_candidate_less_windows_scope_matches_legacy_directory_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: 操作性完整性应排除隐藏目录和缓存目录，并
    # 保留旧版对看似源码的符号链接目录的选择策略。
    import tree_sitter_analyzer.cache.indexer as indexer

    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "ignored.py").write_text("ignored = 1\n", encoding="utf-8")
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "kept.py").write_text("kept = 1\n", encoding="utf-8")
    (tmp_path / "target").mkdir()
    (tmp_path / "module.py").symlink_to(tmp_path / "target", target_is_directory=True)
    (tmp_path / "alias").symlink_to(tmp_path / "target", target_is_directory=True)
    monkeypatch.setattr(indexer, "os", _OsProxy(name="nt"))

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result == {"module.py", "visible/kept.py"}


def test_candidate_less_windows_scope_fails_closed_on_walk_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #1253: 部分遍历不能签发操作性路径相等结论。
    import tree_sitter_analyzer.cache.indexer as indexer

    class WalkErrorProxy(_OsProxy):
        def walk(self, root, onerror=None):
            assert onerror is not None
            onerror(OSError("enumeration denied"))
            return iter(())

    monkeypatch.setattr(indexer, "os", WalkErrorProxy(name="nt"))

    result = indexer._bounded_selected_supported_paths(
        str(tmp_path), 10, None, frozenset()
    )

    assert result is None
