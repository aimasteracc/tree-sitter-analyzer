"""#1376：test_ast_cache_snapshot_validation 行为组；测试主体保留，中文文档和 UTF-8 修正单独校验。"""

import os
from dataclasses import replace

import pytest

import tests.unit._ast_cache_helpers as _fixtures
from tests.unit._ast_cache_helpers import (
    _cache_storage_bytes,
    _python_language,
    _snapshot,
)
from tree_sitter_analyzer.ast_cache import (
    ASTCache,
)
from tree_sitter_analyzer.index_source_snapshot import make_source_scope_descriptor
from tree_sitter_analyzer.indexing_snapshot import (
    IndexCandidateSnapshot,
    IndexFileFingerprint,
    IndexSnapshotEntry,
    build_index_candidate_snapshot,
)

tmp_project = _fixtures.tmp_project
cache = _fixtures.cache
method_project = _fixtures.method_project


def test_force_index_rejects_wrong_root_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = replace(
        _snapshot(tmp_path, path),
        project_root=os.path.abspath(tmp_path / "other"),
    )

    try:
        with pytest.raises(ValueError, match="different project root"):
            cache.index_project(
                max_files=10,
                force=True,
                candidate_snapshot=snapshot,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_snapshot_rejects_candidate_outside_project_root(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes project root"):
        build_index_candidate_snapshot(
            str(project),
            max_files=10,
            exclude_patterns=frozenset(),
            walk_fn=lambda _root: (str(outside),),
            language_fn=lambda _path: "python",
        )


def test_force_index_rejects_fabricated_external_snapshot_entry(tmp_path):
    # PR #1172 review 2026-07-27: 直接提供的快照曾绕过 builder 的包含范围检查。
    project = tmp_path / "project"
    project.mkdir()
    indexed = project / "app.py"
    indexed.write_text("value = 1\n", encoding="utf-8")
    outside = tmp_path / "secret.py"
    outside.write_text("secret = 1\n", encoding="utf-8")
    cache = ASTCache(str(project))
    cache.index_file(str(indexed))
    before = cache.lookup(str(indexed))
    snapshot = IndexCandidateSnapshot(
        project_root=os.path.abspath(project),
        max_files=10,
        entries=(
            IndexSnapshotEntry(
                abs_path=str(outside),
                rel_path="../secret.py",
                language="python",
                decision="selected",
                fingerprint=IndexFileFingerprint.from_stat(outside.stat()),
            ),
        ),
        present_paths=frozenset({"../secret.py"}),
        discovered=1,
        selected=1,
        excluded=0,
        skipped=0,
        errors=0,
        limited=0,
    )

    try:
        with pytest.raises(ValueError, match="escapes project root"):
            cache.index_project(
                max_files=10,
                force=True,
                candidate_snapshot=snapshot,
            )
        after = cache.lookup(str(indexed))
    finally:
        cache.close()

    assert after == before


def test_index_rejects_snapshot_relative_path_mismatch(tmp_path):
    # PR #1172 review 2026-07-27: 缓存键曾可能与绝对路径不一致。
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    snapshot = _snapshot(tmp_path, path)
    malformed = replace(
        snapshot,
        entries=(replace(snapshot.selected_entries[0], rel_path="other.py"),),
    )
    cache = ASTCache(str(tmp_path))

    try:
        with pytest.raises(ValueError, match="relative path mismatch"):
            cache.index_project(max_files=10, candidate_snapshot=malformed)
    finally:
        cache.close()


def test_force_index_rejects_wrong_limit_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = _snapshot(tmp_path, path)

    try:
        with pytest.raises(ValueError, match="different max_files"):
            cache.index_project(
                max_files=11,
                force=True,
                candidate_snapshot=snapshot,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_force_index_rejects_missing_metadata_before_clearing_cache(tmp_path):
    path = tmp_path / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_file(str(path))
    before = cache.lookup(str(path))
    snapshot = _snapshot(tmp_path, path)
    malformed = replace(
        snapshot,
        entries=(replace(snapshot.selected_entries[0], fingerprint=None),),
    )

    try:
        with pytest.raises(ValueError, match="lacks metadata"):
            cache.index_project(
                max_files=10,
                force=True,
                candidate_snapshot=malformed,
            )
        row = cache.lookup(str(path))
    finally:
        cache.close()

    assert row == before


def test_snapshot_preserves_logical_project_root_spelling(tmp_path):
    # PR #1172 review 2026-07-27: realpath 曾破坏 macOS /var 路径的缓存查找。
    physical_root = tmp_path / "physical"
    logical_root = tmp_path / "logical"
    physical_root.mkdir()
    logical_root.symlink_to(physical_root, target_is_directory=True)
    path = logical_root / "app.py"
    path.write_text("value = 1\n", encoding="utf-8")

    snapshot = build_index_candidate_snapshot(
        str(logical_root),
        max_files=10,
        exclude_patterns=frozenset(),
        walk_fn=lambda root: (os.path.join(root, "app.py"),),
        language_fn=_python_language,
    )

    assert snapshot.project_root == os.path.abspath(logical_root)
    assert snapshot.selected_entries[0].abs_path == os.path.abspath(path)
    assert snapshot.selected_entries[0].rel_path == "app.py"


def test_force_index_rejects_scope_mismatch_before_cache_mutation(tmp_path):
    # PR #1253 review 3757240535: 无效的 force 输入不能产生破坏性修改。
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)
    before = _cache_storage_bytes(tmp_path)
    bad_scope = make_source_scope_descriptor(certification_max_files=11)

    try:
        with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_MISMATCH"):
            cache.index_project(
                max_files=10,
                force=True,
                workers=0,
                source_scope=bad_scope,
            )
        after = _cache_storage_bytes(tmp_path)
    finally:
        cache.close()

    assert after == before


def test_force_index_rejects_oversized_exclusions_before_cache_mutation(tmp_path):
    # PR #1253 review 3757240535: 描述符预算失败必须保留缓存。
    source = tmp_path / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    cache = ASTCache(str(tmp_path))
    cache.index_project(workers=0)
    before = _cache_storage_bytes(tmp_path)

    try:
        with pytest.raises(ValueError, match="SOURCE_SCOPE_DESCRIPTOR_TOO_LARGE"):
            cache.index_project(
                max_files=10,
                force=True,
                workers=0,
                exclude_patterns=frozenset({"x" * 70_000}),
            )
        after = _cache_storage_bytes(tmp_path)
    finally:
        cache.close()

    assert after == before
