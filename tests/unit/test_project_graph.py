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
