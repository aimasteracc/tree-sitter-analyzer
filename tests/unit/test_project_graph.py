"""Unit tests for project_graph.py — DependencyGraph, ImportExtractor, BlastRadius."""

from pathlib import Path

import pytest

# Will be imported after implementation
# from tree_sitter_analyzer.project_graph import (
#     DependencyGraph,
#     BlastRadius,
#     extract_imports_from_file,
# )

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "project_graph"
PY_PROJECT = FIXTURES_DIR / "python_project"
JS_PROJECT = FIXTURES_DIR / "js_project"
GO_PROJECT = FIXTURES_DIR / "go_project"
RUST_PROJECT = FIXTURES_DIR / "rust_project"
CPP_PROJECT = FIXTURES_DIR / "cpp_project"
JAVA_PROJECT = FIXTURES_DIR / "java_project"


# ============================================================
# Import extraction tests
# ============================================================


class TestImportExtraction:
    """Test import extraction from source files."""

    def test_extract_python_imports_from_main(self):
        """main.py should yield imports to utils, models.user, models.base, pkg.submodule."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(PY_PROJECT / "main.py"), "python")
        assert imports, "Should extract at least one import"

        # Resolve relative imports
        resolved = set()
        for imp in imports:
            resolved.add(imp.get("module_name", "") or imp.get("resolved_path", ""))

        # Check project-level imports (relative imports get resolved to paths)
        # We expect at least: utils, models.user, models.base, pkg.submodule
        # (os, sys, pathlib are stdlib/external)
        found_internal = {r for r in resolved if "." in r or "/" in r}
        assert len(found_internal) >= 3, (
            f"Expected >=3 internal imports, got {found_internal}"
        )

    def test_extract_python_imports_from_utils(self):
        """utils.py has no imports → empty list."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(PY_PROJECT / "utils.py"), "python")
        # Only count non-stdlib imports
        internal = [i for i in imports if not _is_stdlib(i)]
        assert len(internal) == 0, (
            f"utils.py should have no internal imports, got {internal}"
        )

    def test_extract_js_imports_from_index(self):
        """index.js should yield imports to src/utils, src/models/user, src/formatter."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(JS_PROJECT / "index.js"), "javascript")
        assert imports, "Should extract imports from JS file"

        resolved = {
            i.get("module_name", "") or i.get("resolved_path", "") for i in imports
        }
        assert any("utils" in r or "formatter" in r or "user" in r for r in resolved), (
            f"Expected project imports in {resolved}"
        )

    def test_extract_imports_unsupported_language(self):
        """Unsupported language returns empty list."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(PY_PROJECT / "main.py"), "brainfuck")
        assert imports == []

    def test_extract_go_imports_from_main(self):
        """main.go should yield imports to internal packages, not stdlib."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(GO_PROJECT / "main.go"), "go")
        modules = {i["module_name"] for i in imports}
        assert all("internal" in m for m in modules), (
            f"Expected internal imports only, got {modules}"
        )
        assert "fmt" not in modules, "stdlib fmt should be filtered"

    def test_extract_rust_imports_from_main(self):
        """main.rs should yield crate-local imports, not std."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(
            str(RUST_PROJECT / "src" / "main.rs"), "rust"
        )
        modules = {i["module_name"] for i in imports}
        assert any("crate::" in m for m in modules), (
            f"Expected crate:: imports, got {modules}"
        )
        assert not any("std::" in m for m in modules), (
            f"std should be filtered, got {modules}"
        )

    def test_extract_cpp_imports_from_main(self):
        """main.cpp should yield local includes, not system includes."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(str(CPP_PROJECT / "main.cpp"), "cpp")
        modules = {i["module_name"] for i in imports}
        assert "handler.h" in modules, f"Expected handler.h in {modules}"
        assert "model.h" in modules, f"Expected model.h in {modules}"
        assert all(not m.startswith("<") for m in modules), (
            f"System includes should not have angle brackets: {modules}"
        )

    def test_extract_java_imports_from_main(self):
        """Main.java should yield com.example imports, not java.util."""
        from tree_sitter_analyzer.project_graph import extract_imports_from_file

        imports = extract_imports_from_file(
            str(JAVA_PROJECT / "com" / "example" / "Main.java"), "java"
        )
        modules = {i["module_name"] for i in imports}
        assert any("com.example" in m for m in modules), (
            f"Expected com.example imports, got {modules}"
        )
        assert not any("java.util" in m for m in modules), (
            f"java.util stdlib should be filtered, got {modules}"
        )


# ============================================================
# DependencyGraph tests
# ============================================================


class TestDependencyGraph:
    """Test DependencyGraph construction and queries."""

    @pytest.fixture
    def py_graph(self):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        return DependencyGraph(str(PY_PROJECT))

    @pytest.fixture
    def js_graph(self):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        return DependencyGraph(str(JS_PROJECT))

    def test_build_python_graph(self, py_graph):
        """Graph should contain all .py files in the project."""
        nodes = py_graph.nodes()
        assert len(nodes) > 0, "Graph should have nodes"
        # Should include main.py, utils.py, models/__init__.py, models/base.py, models/user.py, pkg/submodule.py
        assert len(nodes) >= 4, f"Expected >=4 nodes, got {len(nodes)}: {nodes}"

    def test_build_js_graph(self, js_graph):
        """Graph should contain JS files."""
        nodes = js_graph.nodes()
        assert len(nodes) >= 2, f"Expected >=2 nodes, got {len(nodes)}"

    def test_get_dependencies_of_file(self, py_graph):
        """Query what a specific file depends on."""
        deps = py_graph.dependencies_of("main.py")
        assert len(deps) > 0, f"main.py should depend on other files, got {deps}"

    def test_get_dependents_of_file(self, py_graph):
        """Query what files depend on a specific file."""
        # utils.py is imported by main.py
        dependents = py_graph.dependents_of("utils.py")
        assert len(dependents) >= 1, (
            f"utils.py should have dependents, got {dependents}"
        )

    def test_leaf_file_has_no_dependents(self, py_graph):
        """utils.py only has imports from standard library, no internal deps."""
        deps = py_graph.dependencies_of("utils.py")
        # utils.py imports nothing internal
        assert len(deps) == 0, f"utils.py should have no internal deps, got {deps}"

    def test_to_dict_output(self, py_graph):
        """Graph can be serialized to dict."""
        result = py_graph.to_dict()
        assert "nodes" in result
        assert "edges" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_empty_project_handled(self, tmp_path):
        """Empty project directory produces empty graph."""
        from tree_sitter_analyzer.project_graph import DependencyGraph

        empty = tmp_path / "empty_project"
        empty.mkdir()
        graph = DependencyGraph(str(empty))
        assert graph.nodes() == []
        assert graph.edges() == []


# ============================================================
# PR-0.2: symbol_in_degree() — symbol-level fan-in primitive
# ============================================================


class TestSymbolInDegree:
    """Test the PR-0.2 ``symbol_in_degree()`` API.

    The primitive answers "how many project files import this symbol by
    name?" — feeding P4's ranked entry-point detection. RED tests track
    the planner's spec in ``.recon/pr-0-2-design.md``; GREEN tests are
    regression guards on the existing public surface.
    """

    @pytest.fixture
    def py_graph(self):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        return DependencyGraph(str(PY_PROJECT))

    @pytest.fixture
    def custom_graph(self, tmp_path):
        """Build a small focused project for the cases the PY_PROJECT
        fixture doesn't cover (ambiguous defs, repeated imports, etc.).
        """
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "utils.py").write_text(
            "def format_thing(x):\n    return str(x)\n"
            "\n"
            "def never_imported_helper():\n    return None\n",
            encoding="utf-8",
        )
        (tmp_path / "main.py").write_text(
            "from utils import format_thing\n"
            "from utils import format_thing  # duplicate import on purpose\n",
            encoding="utf-8",
        )
        (tmp_path / "cli.py").write_text(
            "from utils import format_thing\n", encoding="utf-8"
        )
        return DependencyGraph(str(tmp_path))

    # ---- RED tests (define the new contract) ----

    def test_R1_simple_fan_in_count(self, custom_graph):
        # main.py and cli.py both import format_thing → file_count = 2.
        result = custom_graph.symbol_in_degree("format_thing")
        assert result.file_count == 2
        assert set(result.importer_files) == {"main.py", "cli.py"}
        # Definitions: utils.py only — not ambiguous.
        assert result.defining_files == ("utils.py",)
        assert result.ambiguous is False

    def test_R2_zero_for_unimported_defined_symbol(self, custom_graph):
        # never_imported_helper is defined in utils.py but no file imports it.
        result = custom_graph.symbol_in_degree("never_imported_helper")
        assert result.file_count == 0
        assert result.importer_files == ()
        assert result.defining_files == ("utils.py",)

    def test_R3_zero_for_unknown_symbol_no_raise(self, custom_graph):
        # Symbol that doesn't exist anywhere — must NOT raise.
        result = custom_graph.symbol_in_degree("xyz_does_not_exist")
        assert result.symbol == "xyz_does_not_exist"
        assert result.file_count == 0
        assert result.importer_files == ()
        assert result.defining_files == ()
        assert result.ambiguous is False

    def test_R4_dedupes_repeated_imports_in_same_file(self, custom_graph):
        # main.py imports format_thing twice → still counts as 1 importer file.
        result = custom_graph.symbol_in_degree("format_thing")
        assert "main.py" in result.importer_files
        # The set was deduped during _build, so main.py appears exactly once.
        assert sum(1 for f in result.importer_files if f == "main.py") == 1

    def test_R5_ambiguous_when_two_files_define_same_name(self, tmp_path):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "a.py").write_text("class Helper: pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("class Helper: pass\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("from a import Helper\n", encoding="utf-8")
        graph = DependencyGraph(str(tmp_path))
        result = graph.symbol_in_degree("Helper")
        assert result.ambiguous is True
        assert set(result.defining_files) == {"a.py", "b.py"}

    def test_R6_disambiguate_by_defining_file(self, tmp_path):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "a.py").write_text("class Helper: pass\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("class Helper: pass\n", encoding="utf-8")
        # one importer per definition
        (tmp_path / "uses_a.py").write_text("from a import Helper\n", encoding="utf-8")
        (tmp_path / "uses_b.py").write_text("from b import Helper\n", encoding="utf-8")
        graph = DependencyGraph(str(tmp_path))

        result_default = graph.symbol_in_degree("Helper")
        assert result_default.file_count == 2  # combined

        result_a_only = graph.symbol_in_degree("Helper", defining_file="a.py")
        assert result_a_only.file_count == 1
        assert result_a_only.importer_files == ("uses_a.py",)

    def test_R7_relative_import_counts(self, py_graph):
        # main.py uses ``from .utils import helper, formatter`` — both
        # named imports must register as importers of those symbols.
        result_helper = py_graph.symbol_in_degree("helper")
        assert "main.py" in result_helper.importer_files
        result_formatter = py_graph.symbol_in_degree("formatter")
        assert "main.py" in result_formatter.importer_files

    def test_R8_stdlib_names_not_indexed(self, py_graph):
        # main.py has ``from pathlib import Path`` — Path lives in
        # stdlib, not the project, so the resolver returns no project
        # file. The `resolved in self._nodes` gate must keep `Path`
        # out of the index.
        result = py_graph.symbol_in_degree("Path")
        assert result.file_count == 0
        assert result.defining_files == ()

    def test_R9_js_bare_imports_yield_no_symbol_entry(self, tmp_path):
        # PR-0.2 ships Python-only symbol extraction; JS files yield
        # no symbol-level data (the import_extractors emit ``names: []``
        # for JS bare imports, so the symbol-importer guard skips them).
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "lib.js").write_text("export function foo() {}\n", encoding="utf-8")
        (tmp_path / "app.js").write_text(
            "import { foo } from './lib';\n", encoding="utf-8"
        )
        graph = DependencyGraph(str(tmp_path))
        # The file-edge layer still works …
        assert "app.js" in graph.dependents_of("lib.js")
        # … but the symbol layer is empty for JS in PR-0.2 (documented
        # limitation; per-language extractors are follow-up PRs).
        assert graph.symbol_in_degree("foo").file_count == 0
        assert graph.symbol_in_degree("foo").defining_files == ()

    # ---- GREEN tests (regression guard on existing surface) ----

    def test_G1_dependents_of_unchanged(self, py_graph):
        # PR-0.2 must not regress file-level dependents_of.
        assert py_graph.dependents_of("utils.py") == ["main.py"]

    def test_G2_to_dict_backward_compatible(self, py_graph):
        result = py_graph.to_dict()
        # All v1 keys still present.
        for key in ("project_root", "nodes", "edges", "node_count", "edge_count"):
            assert key in result, f"existing key {key} dropped from to_dict()"
        # New additive key is present and non-negative.
        assert "symbol_index_size" in result
        assert result["symbol_index_size"] >= 0

    def test_G3_find_cycles_unchanged(self, py_graph):
        # PY_PROJECT has an intentional cycle (used by TestCycleDetection).
        cycles = py_graph.find_cycles()
        assert isinstance(cycles, list)

    def test_G4_no_self_imports_polluting_count(self, tmp_path):
        # ``from . import sub`` resolves to ``sub.py`` AND emits
        # ``names: ["sub"]``. The submodule-as-name guard in _build()
        # must skip this; otherwise every file that does ``from . import
        # sub`` would falsely count itself as a symbol-importer of every
        # name in sub.py.
        from tree_sitter_analyzer.project_graph import DependencyGraph

        (tmp_path / "sub.py").write_text(
            "def real_symbol():\n    pass\n", encoding="utf-8"
        )
        (tmp_path / "main.py").write_text("from . import sub\n", encoding="utf-8")
        graph = DependencyGraph(str(tmp_path))

        # ``sub`` should NOT be in the symbol importer index — it is
        # the module handle, not a symbol from sub.py.
        result = graph.symbol_in_degree("sub")
        # ``sub`` is also the basename of sub.py, so no file should
        # appear as a symbol-importer of the name "sub".
        assert "main.py" not in result.importer_files


# ============================================================
# Cycle detection tests
# ============================================================


class TestCycleDetection:
    """Test circular dependency detection."""

    @pytest.fixture
    def py_graph(self):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        return DependencyGraph(str(PY_PROJECT))

    def test_detect_cycles(self, py_graph):
        """Should detect the cycle between main.py and pkg/submodule.py."""
        cycles = py_graph.find_cycles()
        # submodule.py imports from main.py, and main.py imports from submodule.py
        assert len(cycles) > 0, f"Expected cycles in {PY_PROJECT}, got none"


# ============================================================
# BlastRadius tests
# ============================================================


class TestBlastRadius:
    """Test blast radius / impact analysis."""

    @pytest.fixture
    def py_graph(self):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        return DependencyGraph(str(PY_PROJECT))

    @pytest.fixture
    def radius(self, py_graph):
        from tree_sitter_analyzer.project_graph import BlastRadius

        return BlastRadius(py_graph)

    def test_blast_radius_forward(self, radius):
        """Changing a leaf file → impact propagates to its dependents."""
        # Changing models/base.py should affect user.py and main.py
        impacted = radius.forward("models/base.py")
        assert len(impacted) >= 2, f"Expected >=2 impacted files, got {impacted}"

    def test_blast_radius_reverse(self, radius):
        """To understand what influences a file → trace reverse dependencies."""
        # What does main.py depend on?
        dependencies = radius.reverse("main.py")
        assert len(dependencies) > 0, f"Expected >0 reverse deps, got {dependencies}"

    def test_blast_radius_leaf_file_forward(self, radius):
        """Changing utils.py (no internal deps, imported by main) → only main is impacted."""
        impacted = radius.forward("utils.py")
        assert len(impacted) >= 1, (
            f"utils.py change should impact at least main.py, got {impacted}"
        )

    def test_blast_radius_nonexistent_file(self, radius):
        """Nonexistent file returns empty set."""
        impacted = radius.forward("nonexistent.py")
        assert impacted == set()

    def test_blast_radius_to_dict(self, radius):
        """Can serialize blast radius result."""
        result = radius.analyze("main.py")
        assert "file" in result
        assert "forward_impact" in result
        assert "reverse_dependencies" in result


# ============================================================
# Cache tests
# ============================================================


class TestDependencyGraphCache:
    """Test caching behavior."""

    def test_cache_hit_on_rebuild(self, tmp_path):
        """Rebuilding the same project should use cache (fast second build)."""
        from tree_sitter_analyzer.project_graph import DependencyGraph

        # Create a small project
        proj = tmp_path / "cache_test"
        proj.mkdir()
        (proj / "a.py").write_text("from . import b\n")
        (proj / "b.py").write_text("x = 1\n")

        g1 = DependencyGraph(str(proj))
        g2 = DependencyGraph(str(proj))

        # Both should produce same results
        assert g1.nodes() == g2.nodes()
        assert g1.edges() == g2.edges()


# ============================================================
# Public accessor tests (expose-dependency-graph-public-api)
# ============================================================


class TestDependencyGraphPublicAccessors:
    """TDD: has_node(), node_count(), edge_count() public API."""

    @pytest.fixture
    def small_graph(self, tmp_path):
        from tree_sitter_analyzer.project_graph import DependencyGraph

        proj = tmp_path / "small"
        proj.mkdir()
        (proj / "a.py").write_text("from . import b\n")
        (proj / "b.py").write_text("x = 1\n")
        return DependencyGraph(str(proj))

    def test_has_node_true_for_existing_node(self, small_graph):
        """has_node() returns True for a file that is in the graph."""
        nodes = small_graph.nodes()
        assert len(nodes) >= 1
        assert small_graph.has_node(nodes[0]) is True

    def test_has_node_false_for_missing_node(self, small_graph):
        """has_node() returns False for a file not in the graph."""
        assert small_graph.has_node("nonexistent_file_xyz.py") is False

    def test_node_count_matches_nodes_length(self, small_graph):
        """node_count() equals len(nodes())."""
        assert small_graph.node_count() == len(small_graph.nodes())

    def test_edge_count_matches_edges_length(self, small_graph):
        """edge_count() equals len(edges())."""
        assert small_graph.edge_count() == len(small_graph.edges())

    def test_node_count_nonzero(self, small_graph):
        """A non-empty project has at least one node."""
        assert small_graph.node_count() >= 1


# ============================================================
# Helpers
# ============================================================


def _is_stdlib(import_dict: dict) -> bool:
    """Check if an import is a stdlib module (heuristic)."""
    name = import_dict.get("module_name", "")
    # Common stdlib modules
    stdlib = {
        "os",
        "sys",
        "json",
        "re",
        "pathlib",
        "math",
        "collections",
        "itertools",
        "functools",
        "typing",
        "io",
        "datetime",
    }
    return name in stdlib
