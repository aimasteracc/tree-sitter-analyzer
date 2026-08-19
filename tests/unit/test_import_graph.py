"""Unit tests for the file-level import dependency graph (import_graph.py).

The existing test_import_graph_tool.py mocks ImportGraph entirely, so the real
resolution / graph-algorithm logic (build, blast radius, cycle detection) was
untested (~14% coverage). These tests exercise that logic directly.
"""

from __future__ import annotations

import os

from tree_sitter_analyzer.ast_cache import ASTCache
from tree_sitter_analyzer.import_graph import (
    ImportEdge,
    ImportGraph,
    ImportGraphResult,
    _resolve_js_import,
    _resolve_python_import,
)

ROOT = os.path.normpath("/proj")


def _np(path: str) -> str:
    """Normalize a POSIX-style test path to the host OS separator.

    import_graph resolves via os.path.normpath, so resolved paths use the host
    separator (backslash on Windows). Tests must compare against the same form.
    """
    return os.path.normpath(path)


# ---------------------------------------------------------------------------
# _resolve_python_import — pure resolution logic
# ---------------------------------------------------------------------------


class TestResolvePythonImport:
    def test_bare_dotted_import_resolves_to_module_file(self) -> None:
        assert _resolve_python_import(
            "import pkg.mod", "app.py", {_np("pkg/mod.py")}, ROOT
        ) == _np("pkg/mod.py")

    def test_from_import_resolves_to_submodule(self) -> None:
        assert _resolve_python_import(
            "from pkg.sub import thing", "app.py", {_np("pkg/sub.py")}, ROOT
        ) == _np("pkg/sub.py")

    def test_import_resolves_to_package_init(self) -> None:
        assert _resolve_python_import(
            "import pkg", "app.py", {_np("pkg/__init__.py")}, ROOT
        ) == _np("pkg/__init__.py")

    def test_stdlib_import_is_not_resolved(self) -> None:
        # Even if a same-named file exists, stdlib top-level is excluded.
        assert (
            _resolve_python_import("import os", "app.py", {_np("os.py")}, ROOT) is None
        )

    def test_unresolvable_import_returns_none(self) -> None:
        assert (
            _resolve_python_import(
                "import totally_missing", "app.py", {_np("a.py")}, ROOT
            )
            is None
        )

    def test_relative_import_with_module_resolves_to_sibling(self) -> None:
        result = _resolve_python_import(
            "from .sibling import thing",
            _np("pkg/mod.py"),
            {_np("pkg/sibling.py"), _np("pkg/__init__.py")},
            ROOT,
        )
        assert result == _np("pkg/sibling.py")

    def test_bare_relative_import_is_unresolved(self) -> None:
        # Known limitation: bare `from . import x` (no module after the dot)
        # is not resolved by the current regex set.
        result = _resolve_python_import(
            "from . import sibling",
            _np("pkg/mod.py"),
            {_np("pkg/sibling.py"), _np("pkg/__init__.py")},
            ROOT,
        )
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_js_import — pure resolution logic
# ---------------------------------------------------------------------------


class TestResolveJsImport:
    def test_require_relative(self) -> None:
        assert _resolve_js_import(
            "const u = require('./util')",
            _np("src/app.js"),
            {_np("src/util.js")},
            ROOT,
        ) == _np("src/util.js")

    def test_esm_import_relative(self) -> None:
        assert _resolve_js_import(
            "import u from './util'",
            _np("src/app.js"),
            {_np("src/util.ts")},
            ROOT,
        ) == _np("src/util.ts")

    def test_index_resolution(self) -> None:
        assert _resolve_js_import(
            "import x from './widget'",
            _np("src/app.js"),
            {_np("src/widget/index.js")},
            ROOT,
        ) == _np("src/widget/index.js")

    def test_mts_sibling_resolution(self) -> None:
        """An extensionless import must probe the ``.mts`` sibling."""
        assert _resolve_js_import(
            "import { run } from './util'",
            _np("src/app.mts"),
            {_np("src/util.mts")},
            ROOT,
        ) == _np("src/util.mts")

    def test_mjs_sibling_resolution(self) -> None:
        """An extensionless import must probe the ``.mjs`` sibling."""
        assert _resolve_js_import(
            "import { run } from './util'",
            _np("src/app.mjs"),
            {_np("src/util.mjs")},
            ROOT,
        ) == _np("src/util.mjs")

    def test_cts_sibling_resolution(self) -> None:
        """An extensionless import must probe the ``.cts`` sibling."""
        assert _resolve_js_import(
            "const u = require('./util')",
            _np("src/app.cts"),
            {_np("src/util.cts")},
            ROOT,
        ) == _np("src/util.cts")

    def test_cjs_index_resolution(self) -> None:
        """A directory import must probe ``<dir>/index.cjs``."""
        assert _resolve_js_import(
            "const w = require('./widget')",
            _np("src/app.cjs"),
            {_np("src/widget/index.cjs")},
            ROOT,
        ) == _np("src/widget/index.cjs")

    def test_bare_module_not_resolved(self) -> None:
        assert (
            _resolve_js_import(
                "import react from 'react'",
                _np("src/app.js"),
                {_np("src/util.js")},
                ROOT,
            )
            is None
        )


# ---------------------------------------------------------------------------
# ImportGraph graph algorithms — built via injected edges
# ---------------------------------------------------------------------------


def _graph(edges: list[tuple[str, str]]) -> ImportGraph:
    """Construct an already-built ImportGraph from (source, target) pairs."""
    g = ImportGraph(ROOT)
    for src, tgt in edges:
        edge = ImportEdge(
            source_file=src, target_file=tgt, import_text=f"import {tgt}", line=0
        )
        g._edges.append(edge)
        g._forward.setdefault(src, []).append(edge)
        g._reverse.setdefault(tgt, []).append(edge)
        g._project_files.update([src, tgt])
    g._built = True
    return g


class TestImportGraphQueries:
    def test_dependencies_of_forward(self) -> None:
        g = _graph([("a.py", "b.py"), ("a.py", "c.py")])
        targets = {d["target"] for d in g.dependencies_of("a.py")}
        assert targets == {"b.py", "c.py"}

    def test_dependents_of_reverse(self) -> None:
        g = _graph([("a.py", "c.py"), ("b.py", "c.py")])
        sources = {d["source"] for d in g.dependents_of("c.py")}
        assert sources == {"a.py", "b.py"}

    def test_dependents_of_unknown_file_is_empty(self) -> None:
        g = _graph([("a.py", "b.py")])
        assert g.dependents_of("nope.py") == []

    def test_blast_radius_transitive(self) -> None:
        # c <- b <- a  (changing c affects b and a)
        g = _graph([("b.py", "c.py"), ("a.py", "b.py")])
        result = g.blast_radius("c.py")
        assert result["direct_dependents"] == 1
        assert result["transitive_dependents"] == 2
        affected = {f["file"] for f in result["affected_files"]}
        assert affected == {"a.py", "b.py"}

    def test_blast_radius_respects_max_depth(self) -> None:
        g = _graph([("b.py", "c.py"), ("a.py", "b.py")])
        result = g.blast_radius("c.py", max_depth=1)
        # depth 1 reaches b only, not the transitive a
        affected = {f["file"] for f in result["affected_files"]}
        assert "b.py" in affected
        assert "a.py" not in affected

    def test_detect_cycles(self) -> None:
        g = _graph([("a.py", "b.py"), ("b.py", "a.py")])
        result = g._make_result()
        assert any(set(cycle) >= {"a.py", "b.py"} for cycle in result.cycles)

    def test_no_cycles_in_dag(self) -> None:
        g = _graph([("a.py", "b.py"), ("b.py", "c.py")])
        assert g._make_result().cycles == []

    def test_summary_statistics(self) -> None:
        g = _graph([("a.py", "c.py"), ("b.py", "c.py"), ("a.py", "b.py")])
        summary = g.summary()
        assert summary["edge_count"] == 3
        assert summary["files_with_imports"] == 2  # a, b
        assert summary["files_imported_by_others"] == 2  # b, c
        most_imported = dict(summary["most_imported"])
        assert most_imported["c.py"] == 2


# ---------------------------------------------------------------------------
# build() — end-to-end against a fake AST cache
# ---------------------------------------------------------------------------


class TestImportGraphBuild:
    def test_build_resolves_edges_from_cache(self, monkeypatch) -> None:
        imports = {
            "a.py": ["import b"],
            "b.py": ["import os"],  # stdlib -> no edge
        }

        class _FakeCache:
            def __init__(self, root: str) -> None:
                pass

            def get_imports(self) -> dict[str, list[str]]:
                return imports

            def close(self) -> None:
                pass

        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", _FakeCache)
        graph = ImportGraph(ROOT)
        result = graph.build()

        assert isinstance(result, ImportGraphResult)
        assert result.edge_count == 1
        assert result.edges[0].source_file == "a.py"
        assert result.edges[0].target_file == "b.py"

    def test_build_resolves_esm_import_from_mts_file(self, monkeypatch) -> None:
        """PUBLIC API: an ESM import in a .mts file must produce an edge.

        Regression for the Codex finding on #1312: ``_resolve_import``
        dispatched on the text prefix, and ``import { run } from './util'``
        starts with ``import `` — so ESM statements were routed to the PYTHON
        resolver and never reached ``_resolve_js_import``. Unit tests on the
        private helper passed while ``health action=imports`` still dropped
        every ESM edge, which is the dominant form in .mjs/.mts files.
        """
        imports = {
            "src/app.mts": ["import { run } from './util'"],
            "src/util.mts": [],
        }

        class _FakeCache:
            def __init__(self, root: str) -> None:
                pass

            def get_imports(self) -> dict[str, list[str]]:
                return imports

            def close(self) -> None:
                pass

        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", _FakeCache)
        result = ImportGraph(ROOT).build()

        assert result.edge_count == 1
        assert result.edges[0].target_file == "src/util.mts"

    def test_build_resolves_esm_import_from_mjs_file(self, monkeypatch) -> None:
        """PUBLIC API: same dispatch path for the .mjs/JavaScript family."""
        imports = {
            "src/app.mjs": ["import { run } from './util'"],
            "src/util.mjs": [],
        }

        class _FakeCache:
            def __init__(self, root: str) -> None:
                pass

            def get_imports(self) -> dict[str, list[str]]:
                return imports

            def close(self) -> None:
                pass

        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", _FakeCache)
        result = ImportGraph(ROOT).build()

        assert result.edge_count == 1
        assert result.edges[0].target_file == "src/util.mjs"

    def test_build_still_resolves_python_import_from_py_file(self, monkeypatch) -> None:
        """Guard: language-based dispatch must not break Python resolution."""
        imports = {
            "pkg/a.py": ["from pkg.b import thing"],
            "pkg/b.py": [],
        }

        class _FakeCache:
            def __init__(self, root: str) -> None:
                pass

            def get_imports(self) -> dict[str, list[str]]:
                return imports

            def close(self) -> None:
                pass

        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", _FakeCache)
        result = ImportGraph(ROOT).build()

        assert result.edge_count == 1
        assert result.edges[0].target_file == "pkg/b.py"

    def test_build_over_real_indexed_mts_project_produces_edge(self, tmp_path) -> None:
        """END-TO-END: real ASTCache index, no fake cache, no path massaging.

        This is the test that actually proves the feature. The fake-cache tests
        above passed while ``ImportGraph`` still produced ZERO edges against a
        real index, because the cache keys paths POSIX-style while both
        resolvers built candidates with ``os.path.normpath`` (backslashes on
        Windows) — so every nested project resolved to nothing. Asserting
        through the real indexer is what surfaced it. (#1312 Codex follow-up.)
        """
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "util.mts").write_text(
            "export function run(v: number): number {\n    return v + 1;\n}\n"
        )
        (tmp_path / "src" / "app.mts").write_text(
            'import { run } from "./util";\nexport function main() {\n'
            "    return run(1);\n}\n"
        )

        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        result = ImportGraph(str(tmp_path)).build()

        assert result.edge_count == 1
        assert result.edges[0].source_file == "src/app.mts"
        assert result.edges[0].target_file == "src/util.mts"

    def test_build_over_real_indexed_nested_python_produces_edge(
        self, tmp_path
    ) -> None:
        """END-TO-END guard: the same separator fix must keep Python working."""
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "b.py").write_text("def bar():\n    return 1\n")
        (tmp_path / "pkg" / "a.py").write_text(
            "from pkg.b import bar\n\n\ndef foo():\n    return bar()\n"
        )

        cache = ASTCache(str(tmp_path))
        cache.index_project(max_files=50)
        cache.close()

        result = ImportGraph(str(tmp_path)).build()

        assert result.edge_count == 1
        assert result.edges[0].source_file == "pkg/a.py"
        assert result.edges[0].target_file == "pkg/b.py"

    def test_build_handles_cache_failure_gracefully(self, monkeypatch) -> None:
        class _BoomCache:
            def __init__(self, root: str) -> None:
                raise RuntimeError("cache unavailable")

        monkeypatch.setattr("tree_sitter_analyzer.ast_cache.ASTCache", _BoomCache)
        result = ImportGraph(ROOT).build()
        assert result.edge_count == 0
        assert result.edges == []
