"""单文件稳定失败不冻结已发布索引；临时失败仍失败闭合（#1554 风险 4）。

RFC-0032 slice 1 评审（2026-10-14）：首次发布接受带单文件失败的部分结果，但其后
只发布无失败结果，含永久失败文件（缺可选语法、同一字节解析失败）的项目首发后不再
更新——相对旧原地路由的回退。
"""

import os
import sqlite3
from types import SimpleNamespace

import pytest

_A = "def alpha():\n    return 1\n"
_A_EDITED = "def alpha_edited():\n    return 2\n"
_B = "def beta():\n    return 3\n"
_BROKEN = "def broken():\n    return 4\n"
_STABLE_REASON = (
    'Swift grammar not installed — pip install "tree-sitter-analyzer[swift]"'
)


@pytest.fixture
def root(tmp_path, monkeypatch):
    """含一个永久解析失败文件的项目；失败由真实解析器入口按文件名注入。"""
    from tree_sitter_analyzer.core.parser import Parser
    from tree_sitter_analyzer.mcp.utils import auto_index_guard

    project = tmp_path / "project"
    project.mkdir()
    (project / "a.py").write_text(_A, encoding="utf-8")
    (project / "b.py").write_text(_B, encoding="utf-8")
    (project / "broken.py").write_text(_BROKEN, encoding="utf-8")
    original = Parser.parse_code

    def parse_code(self, source_code, language, filename=None, *args, **kwargs):
        if filename is not None and os.path.basename(filename) == "broken.py":
            return SimpleNamespace(success=False, error_message=_STABLE_REASON)
        return original(self, source_code, language, filename, *args, **kwargs)

    monkeypatch.setattr(Parser, "parse_code", parse_code)
    auto_index_guard.reset()
    yield str(project)
    auto_index_guard.reset()


def _sync(root):
    from tree_sitter_analyzer.ast_cache import ASTCache
    from tree_sitter_analyzer.incremental_sync import IncrementalSync
    from tree_sitter_analyzer.index_source_scope import make_source_scope_descriptor

    scope = make_source_scope_descriptor()
    cache = ASTCache(root)
    try:
        return IncrementalSync(cache).sync(
            max_files=scope.certification_max_files,
            exclude_patterns=scope.effective_excludes,
            source_scope=scope,
        )
    finally:
        cache.close()


def _index_project(root):
    from tree_sitter_analyzer.ast_cache import ASTCache

    cache = ASTCache(root)
    try:
        return cache.index_project(workers=0)
    finally:
        cache.close()


def _published_state(root):
    """已发布版本的 (函数名, 清单行数)；清单为空即快照不认证为 complete。"""
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    location = resolve_index_location(root)
    assert location.published is True
    connection = sqlite3.connect(location.path.as_uri() + "?mode=ro", uri=True)
    try:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM ast_symbol_rows ORDER BY name"
            )
        ]
        manifests = connection.execute(
            "SELECT COUNT(*) FROM ast_index_snapshot_manifest"
        ).fetchone()[0]
    finally:
        connection.close()
    return names, manifests


def _edit_a(root):
    path = os.path.join(root, "a.py")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(_A_EDITED)
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 2_000_000_000))


def test_sync_after_first_publication_publishes_edit_beside_stable_failure(root):
    first = _sync(root)
    _edit_a(root)
    second = _sync(root)
    assert (
        (first.errors, first.scope_complete),
        (second.errors, second.scope_complete),
        _published_state(root),
    ) == ((1, False), (1, False), (["alpha_edited", "beta"], 0))


def test_index_project_after_first_publication_publishes_edit_beside_stable_failure(
    root,
):
    first = _index_project(root)
    _edit_a(root)
    second = _index_project(root)
    assert (first["errors"], second["errors"], _published_state(root)) == (
        1,
        1,
        (["alpha_edited", "beta"], 0),
    )


def test_transient_failure_after_first_publication_keeps_parent(root, monkeypatch):
    # 临时读失败可能只是一瞬的锁或权限；不能用丢失该文件的结果替换父版本。
    from tree_sitter_analyzer.ast_cache import ASTCache

    _sync(root)
    _edit_a(root)
    original = ASTCache.index_file

    def deny_a(self, file_path, *args, **kwargs):
        if os.path.basename(file_path) == "a.py":
            return {"file": "a.py", "status": "error", "reason": "Permission denied"}
        return original(self, file_path, *args, **kwargs)

    monkeypatch.setattr(ASTCache, "index_file", deny_a)
    second = _sync(root)
    assert (second.errors, _published_state(root)) == (2, (["alpha", "beta"], 0))


def test_stable_failures_only_requires_every_error_to_be_a_stable_file_detail():
    from tree_sitter_analyzer.cache.publication_policy import (
        FAILURE_KIND,
        STABLE,
        stable_failures_only,
    )

    stable = {"file": "x.swift", "status": "error", FAILURE_KIND: STABLE}
    transient = {"file": "y.py", "status": "error", "reason": "Permission denied"}
    fileless = {"file": "", "status": "error", FAILURE_KIND: STABLE}
    assert (
        stable_failures_only([stable], 1),
        stable_failures_only([stable], 2),
        stable_failures_only([stable, transient], 2),
        stable_failures_only([fileless], 1),
        stable_failures_only([], 0),
    ) == (True, False, False, False, False)


@pytest.mark.parametrize("route", ["sync", "index_project"])
def test_stable_failure_after_complete_parent_revokes_certification(root, route):
    # 父版本已认证 complete；新出现的稳定失败文件发布后不得沿用父版本清单与调用图标记。
    from tree_sitter_analyzer.cache.callgraph_state import exact_call_graph_marker
    from tree_sitter_analyzer.cache.generation_routing import resolve_index_location

    broken = os.path.join(root, "broken.py")
    os.replace(broken, broken + ".off")
    assert _sync(root).scope_complete is True
    before = _published_state(root)
    os.replace(broken + ".off", broken)
    _edit_a(root)
    result = _sync(root) if route == "sync" else _index_project(root)
    errors = result.errors if route == "sync" else result["errors"]
    connection = sqlite3.connect(
        resolve_index_location(root).path.as_uri() + "?mode=ro", uri=True
    )
    try:
        marker = exact_call_graph_marker(connection)
    finally:
        connection.close()
    assert (before, errors, _published_state(root), marker) == (
        (["alpha", "beta"], 1),
        1,
        (["alpha_edited", "beta"], 0),
        False,
    )
