"""Tests for cached dependency graph reconstruction used by change-impact."""

from __future__ import annotations

import os
import sqlite3

import pytest

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.cache.schema import CURRENT_SCHEMA_VERSION
from tree_sitter_analyzer.mcp.tools.utils import change_impact_cached_graph as cached
from tree_sitter_analyzer.mcp.tools.utils.change_impact_analysis import (
    _load_dependency_graph,
)
from tree_sitter_analyzer.mcp.tools.utils.change_impact_cached_graph import (
    CachedDependencyGraph,
)


def _index_project(root) -> None:
    cache = ASTCache(str(root))
    try:
        cache.index_project(max_files=20)
    finally:
        cache.close()


def test_load_cached_dependency_graph_returns_none_without_cache(tmp_path):
    assert cached.load_cached_dependency_graph(str(tmp_path)) is None
    assert cached.load_cached_dependency_graph(None) is None


def test_cached_dependency_graph_resolves_python_relative_edges(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text(
        "from .b import helper\n\n\ndef run():\n    return helper()\n",
        encoding="utf-8",
    )
    (pkg / "b.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    _index_project(tmp_path)

    graph = _load_dependency_graph(str(tmp_path))

    assert graph is not None
    assert graph.dependencies_of("pkg/a.py") == ["pkg/b.py"]
    assert graph.dependents_of("pkg/b.py") == ["pkg/a.py"]


def test_cached_dependency_graph_resolves_js_relative_edges(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.js").write_text(
        "import { format } from './formatter';\nformat('x');\n",
        encoding="utf-8",
    )
    (src / "formatter.js").write_text(
        "export function format(value) { return value; }\n",
        encoding="utf-8",
    )
    _index_project(tmp_path)

    graph = _load_dependency_graph(str(tmp_path))

    assert graph is not None
    assert graph.dependencies_of("src/index.js") == ["src/formatter.js"]
    assert graph.dependents_of("src/formatter.js") == ["src/index.js"]


def test_cached_dependency_graph_methods_ignore_invalid_edges(tmp_path):
    graph = CachedDependencyGraph(str(tmp_path), {"a.py", "b.py"})

    graph.add_edge("a.py", "a.py")
    graph.add_edge("a.py", "missing.py")
    graph.add_edge("a.py", "b.py")

    assert graph.nodes() == ["a.py", "b.py"]
    assert graph.edges() == [("a.py", "b.py")]
    assert graph.dependencies_of("a.py") == ["b.py"]
    assert graph.dependents_of("b.py") == ["a.py"]


def test_cached_import_module_parsers_cover_supported_languages():
    assert cached._modules_from_import_text(
        "from . import sibling as sib", "python", "pkg/a.py"
    ) == [(".sibling", True)]
    assert cached._modules_from_import_text(
        "import mod from './mod';\nconst x = require('./x')",
        "typescript",
        "src/a.ts",
    ) == [("./mod", True), ("./x", True)]
    assert cached._modules_from_import_text(
        "import java.util.List;\nimport com.example.Handler;",
        "java",
        "src/Main.java",
    ) == [("com.example.Handler", False)]
    assert cached._modules_from_import_text(
        'import (\n  "fmt"\n  "./internal/handler"\n)',
        "go",
        "main.go",
    ) == [("fmt", False), ("./internal/handler", True)]
    assert cached._modules_from_import_text(
        "use crate::handler::serve;\nuse external::thing;",
        "rust",
        "src/main.rs",
    ) == [("crate::handler::serve", True), ("external::thing", False)]
    assert cached._modules_from_import_text(
        '#include "local.h"\n#include <stdio.h>', "c", "main.c"
    ) == [("local.h", True)]
    assert cached._modules_from_import_text("ignored", "ruby", "app.rb") == []


def test_iter_cached_import_modules_handles_invalid_json_and_dict_rows():
    assert cached._iter_cached_import_modules({"imports_json": "["}) == []
    assert cached._iter_cached_import_modules(
        {
            "file_path": "pkg/a.py",
            "language": "python",
            "imports_json": '[{"text": "from .b import helper"}, ""]',
        }
    ) == [(".b", True)]


def test_cached_index_rows_handles_query_failure():
    class BadConn:
        def execute(self, query):
            raise RuntimeError("boom")

    assert cached._cached_index_rows(BadConn()) == []


def test_add_cached_import_edges_ignores_unsupported_languages(tmp_path):
    graph = CachedDependencyGraph(str(tmp_path), {"a.rb"})

    cached._add_cached_import_edges(
        graph,
        {"file_path": "a.rb", "language": "ruby", "imports_json": '["require x"]'},
        {"a.rb"},
    )

    assert graph.edges() == []


def test_add_cached_import_edges_normalizes_windows_resolver_paths(
    tmp_path, monkeypatch
):
    graph = CachedDependencyGraph(str(tmp_path), {"src/index.js", "src/formatter.js"})
    monkeypatch.setitem(
        cached._IMPORT_RESOLVERS,
        "javascript",
        lambda module, source, nodes, is_relative: "src\\formatter.js",
    )

    cached._add_cached_import_edges(
        graph,
        {
            "file_path": "src/index.js",
            "language": "javascript",
            "imports_json": "[\"import { format } from './formatter';\"]",
        },
        {"src/index.js", "src/formatter.js"},
    )

    assert graph.dependencies_of("src/index.js") == ["src/formatter.js"]


def test_cached_graph_does_not_recreate_removed_database(tmp_path, monkeypatch):
    """存在检查后消失的索引应回退，不能被查询重新创建。"""
    _index_project(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    connect = sqlite3.connect

    def remove_then_connect(*args, **kwargs):
        db_path.unlink()
        return connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", remove_then_connect)
    assert cached.load_cached_dependency_graph(str(tmp_path)) is None
    assert not db_path.exists()


@pytest.mark.parametrize("version", [1, CURRENT_SCHEMA_VERSION + 1])
def test_cached_graph_does_not_migrate_incompatible_database(tmp_path, version):
    """旧版或未来版本索引保持原状，由调用方回退到源码分析。"""
    (tmp_path / "a.py").write_text("value = 1\n", encoding="utf-8")
    _index_project(tmp_path)
    db_path = tmp_path / ".ast-cache" / "index.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM ast_schema_version")
        conn.execute(
            "INSERT INTO ast_schema_version(version, applied_at, description) "
            "VALUES (?, 0, 'test')",
            (version,),
        )
        conn.commit()
        before = list(conn.iterdump())
        assert cached.load_cached_dependency_graph(str(tmp_path)) is None
        assert list(conn.iterdump()) == before
    finally:
        conn.close()


@pytest.mark.parametrize("change", ["rewrite", "add", "delete"])
def test_cached_graph_rejects_changed_source_inventory(tmp_path, change):
    """缓存准入必须发现等时间戳改写及文件增删。"""
    importer = tmp_path / "a.py"
    importer.write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("value = 2\n", encoding="utf-8")
    _index_project(tmp_path)
    if change == "rewrite":
        before = importer.stat()
        importer.write_text("import c\n", encoding="utf-8")
        os.utime(importer, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif change == "add":
        (tmp_path / "d.py").write_text("import c\n", encoding="utf-8")
    else:
        importer.unlink()
    assert cached.load_cached_dependency_graph(str(tmp_path)) is None


def test_cached_graph_admission_matches_native_source_capability(tmp_path):
    """具备源码认证能力时复用缓存，否则明确回退。"""
    from tree_sitter_analyzer.index_source_snapshot import (
        capture_current_source_snapshot,
    )

    (tmp_path / "a.py").write_text("value = 1\n", encoding="utf-8")
    _index_project(tmp_path)
    evidence = capture_current_source_snapshot(str(tmp_path))
    graph = cached.load_cached_dependency_graph(str(tmp_path))
    if os.name == "posix" and os.path.exists("/dev/fd"):
        assert evidence.state == "exact"
        assert graph is not None
        assert graph.nodes() == ["a.py"]
    else:
        assert evidence.reason == "SOURCE_SCOPE_UNSUPPORTED"
        assert graph is None
    assert _load_dependency_graph(str(tmp_path)).nodes() == ["a.py"]


def test_cached_graph_rejects_unavailable_source_evidence(tmp_path, monkeypatch):
    """认证不可用不能继续返回缓存图，源码分析仍可使用。"""
    from tree_sitter_analyzer.index_source_snapshot import CurrentSourceSnapshot

    (tmp_path / "a.py").write_text("value = 1\n", encoding="utf-8")
    _index_project(tmp_path)
    monkeypatch.setattr(
        cached,
        "capture_current_source_snapshot",
        lambda _root: CurrentSourceSnapshot(frozenset(), None, None, "unknown", "test"),
    )
    assert cached.load_cached_dependency_graph(str(tmp_path)) is None
    assert _load_dependency_graph(str(tmp_path)).nodes() == ["a.py"]


def test_repeated_change_impact_tracks_preserved_mtime_imports(tmp_path):
    """同一工具实例反复处理修改时，磁盘与内存缓存不能落后一次。"""
    import asyncio
    import subprocess

    from tree_sitter_analyzer.mcp.tools.change_impact_tool import ChangeImpactTool

    for name, text in {
        "a.py": "import b\n",
        "b.py": "value = 1\n",
        "c.py": "value = 2\n",
    }.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    for command in (
        ["git", "init", "-q"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=TSA Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "baseline",
        ],
    ):
        subprocess.run(command, cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "c.py").write_text("value = 3\n", encoding="utf-8")
    _index_project(tmp_path)
    tool = ChangeImpactTool(str(tmp_path))
    for module in ("b", "c", "b", "c", "b"):
        path = tmp_path / "a.py"
        before = path.stat()
        path.write_text(f"import {module}\n", encoding="utf-8")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = asyncio.run(tool.execute({"mode": "diff", "output_format": "json"}))
        assert result["success"] is True
        impact = next(row for row in result["file_impacts"] if row["file"] == "c.py")
        assert impact["direct_dependents"] == (["a.py"] if module == "c" else [])


@pytest.mark.parametrize(
    "column,value",
    [
        ("extractor_version", 0),
        (
            "symbols_json",
            '{"truncated_depth":true,"import_projection_complete":true,"syntax_error":false}',
        ),
        (
            "symbols_json",
            '{"truncated_depth":false,"import_projection_complete":false,"syntax_error":false}',
        ),
        (
            "symbols_json",
            '{"truncated_depth":false,"import_projection_complete":true,"syntax_error":true}',
        ),
        ("symbols_json", "[]"),
        ("imports_json", "{"),
        ("imports_json", "{}"),
        # PR #1417 审查：列表成员的文本缺失或类型错误也必须拒绝。
        ("imports_json", '[{"line":1}]'),
        ("imports_json", "[42]"),
        ("imports_json", '[{"text":7}]'),
    ],
)
def test_cached_graph_rejects_invalid_extraction_evidence(tmp_path, column, value):
    """源码哈希相同也不能复用旧提取器或不完整、损坏的导入证据。"""
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value = 1\n", encoding="utf-8")
    _index_project(tmp_path)
    conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
    try:
        conn.execute(
            f"UPDATE ast_index SET {column} = ? WHERE file_path = 'a.py'", (value,)
        )
        conn.commit()
    finally:
        conn.close()
    assert cached.load_cached_dependency_graph(str(tmp_path)) is None
    assert _load_dependency_graph(str(tmp_path)).dependencies_of("a.py") == ["b.py"]


@pytest.mark.parametrize(
    "imports_json,expected_rows",
    [
        ('["import b"]', 2),
        ('[{"text":"import b"}]', 2),
        ('[{"line":1}]', 0),
        ("[42]", 0),
        ('[{"text":7}]', 0),
    ],
)
def test_cached_import_row_admission_checks_each_entry(
    tmp_path, imports_json, expected_rows
):
    """在源码捕获平台判断之前，直接校验每个导入成员的文本类型。"""
    # PR #1417 审查：顶层列表校验无法发现损坏成员。
    (tmp_path / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("value=1\n", encoding="utf-8")
    _index_project(tmp_path)
    conn = sqlite3.connect(tmp_path / ".ast-cache" / "index.db")
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "UPDATE ast_index SET imports_json=? WHERE file_path='a.py'",
            (imports_json,),
        )
        assert len(cached._cached_index_rows(conn)) == expected_rows
    finally:
        conn.close()
