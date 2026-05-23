"""Tests for dead_code_analyzer — transitive dead code, unused imports, unreferenced variables."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.dead_code_analyzer import (
    DeadCodeResult,
    DeadFunction,
    UnreferencedVariable,
    UnusedImport,
    _is_known_entry,
    _is_test_file,
    analyze_dead_code,
    find_transitive_dead_code,
    find_unused_imports,
    find_unreferenced_variables,
)


# ---------------------------------------------------------------------------
# _is_test_file
# ---------------------------------------------------------------------------

class TestIsTestFile:
    def test_prefixed_test_file(self) -> None:
        assert _is_test_file("test_foo.py") is True

    def test_suffixed_test_file(self) -> None:
        assert _is_test_file("foo_test.py") is True

    def test_spec_file(self) -> None:
        assert _is_test_file("bar.spec.ts") is True

    def test_test_directory(self) -> None:
        assert _is_test_file("tests/test_main.py") is True

    def test_regular_file(self) -> None:
        assert _is_test_file("src/main.py") is False

    def test_nested_test_dir(self) -> None:
        assert _is_test_file("project/tests/helper.py") is True


# ---------------------------------------------------------------------------
# _is_known_entry
# ---------------------------------------------------------------------------

class TestIsKnownEntry:
    def test_python_main(self) -> None:
        assert _is_known_entry("main", "python") is True

    def test_python_setup(self) -> None:
        assert _is_known_entry("setup", "python") is True

    def test_java_init(self) -> None:
        assert _is_known_entry("init", "java") is True

    def test_javascript_handler(self) -> None:
        assert _is_known_entry("handler", "javascript") is True

    def test_go_testmain(self) -> None:
        assert _is_known_entry("TestMain", "go") is True

    def test_unknown_language(self) -> None:
        assert _is_known_entry("main", "rust") is False

    def test_non_entry_name(self) -> None:
        assert _is_known_entry("helper_func", "python") is False


# ---------------------------------------------------------------------------
# find_transitive_dead_code
# ---------------------------------------------------------------------------

class TestFindTransitiveDeadCode:
    """Test transitive dead-code detection via a mock CallGraph."""

    @pytest.fixture()
    def simple_graph(self, tmp_path):
        """Create a project with two files: one calling the other."""
        # TODO: build a minimal CallGraph fixture
        # main.py defines caller(), which calls callee()
        # callee.py defines callee(), nobody calls it externally
        pass

    def test_finds_root_dead_function(self, simple_graph) -> None:
        """Functions never called from outside should be flagged dead."""
        # TODO: assert DeadFunction with reason='unreachable'
        pass

    def test_propagates_to_callees(self, simple_graph) -> None:
        """Functions only called from dead functions should also be dead."""
        # TODO: verify transitive depth > 0
        pass

    def test_excludes_test_files_when_flag_set(self, simple_graph) -> None:
        """When include_test_files=False, test-file functions are excluded."""
        pass

    def test_entry_points_are_not_dead(self, simple_graph) -> None:
        """Known entry-point names should not be flagged."""
        pass


# ---------------------------------------------------------------------------
# find_unused_imports
# ---------------------------------------------------------------------------

class TestFindUnusedImports:
    def test_detects_unused_import(self, tmp_path) -> None:
        """A file importing `os` but never referencing it should report unused."""
        py = tmp_path / "a.py"
        py.write_text("import os\n\ndef foo():\n    pass\n")
        # TODO: call find_unused_imports and assert UnusedImport for 'os'
        pass

    def test_used_import_not_flagged(self, tmp_path) -> None:
        """An import that IS referenced in code should not be flagged."""
        py = tmp_path / "b.py"
        py.write_text("import os\n\ndef foo():\n    return os.path.join('a', 'b')\n")
        pass

    def test_multiple_unused_names(self, tmp_path) -> None:
        """`from x import a, b, c` where only a is used should flag b, c."""
        py = tmp_path / "c.py"
        py.write_text("from os.path import join, exists, isfile\n\ndef f():\n    return join('a')\n")
        pass

    def test_unreadable_file_returns_empty(self, tmp_path) -> None:
        """A binary or unreadable file should produce an empty list, not crash."""
        pass


# ---------------------------------------------------------------------------
# find_unreferenced_variables
# ---------------------------------------------------------------------------

class TestFindUnreferencedVariables:
    def test_detects_unreferenced_assignment(self, tmp_path) -> None:
        """A module-level variable never referenced should be flagged."""
        pass

    def test_referenced_variable_not_flagged(self, tmp_path) -> None:
        """A variable used in a function body should NOT be flagged."""
        pass

    def test_class_attribute_not_flagged_as_unreferenced(self, tmp_path) -> None:
        """Class body assignments are NOT module-level variables."""
        pass


# ---------------------------------------------------------------------------
# analyze_dead_code (top-level)
# ---------------------------------------------------------------------------

class TestAnalyzeDeadCode:
    def test_returns_dead_code_result(self, tmp_path) -> None:
        """Top-level entry should return a DeadCodeResult."""
        py = tmp_path / "simple.py"
        py.write_text("import os\n\ndef dead():\n    pass\n")
        # TODO: result = analyze_dead_code(tmp_path, ...)
        # assert isinstance(result, DeadCodeResult)
        pass

    def test_stats_populated(self, tmp_path) -> None:
        """The stats dict should contain file/function counts."""
        pass

    def test_excludes_dirs(self, tmp_path) -> None:
        """node_modules/.git etc. should be excluded from analysis."""
        pass


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestDeadCodeErrorHandling:
    def test_nonexistent_directory_returns_empty(self) -> None:
        """Passing a path that does not exist should not crash."""
        pass

    def test_binary_file_skipped(self, tmp_path) -> None:
        """Binary files should be silently skipped."""
        pass

    def test_symlink_handled(self, tmp_path) -> None:
        """Symlinked files should not cause infinite loops."""
        pass
