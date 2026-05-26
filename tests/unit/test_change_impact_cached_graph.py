"""Tests for cached dependency graph reconstruction used by change-impact."""

from __future__ import annotations

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.mcp.tools.utils import change_impact_cached_graph as cached
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

    graph = cached.load_cached_dependency_graph(str(tmp_path))

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

    graph = cached.load_cached_dependency_graph(str(tmp_path))

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

    class BadCache:
        def _get_conn(self):
            return BadConn()

    assert cached._cached_index_rows(BadCache()) == []


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
