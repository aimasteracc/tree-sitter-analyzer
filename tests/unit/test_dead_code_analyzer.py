"""Tests for dead_code_analyzer — transitive dead code, unused imports, unreferenced variables."""

from __future__ import annotations

import pytest

from tree_sitter_analyzer.call_graph import CallGraph
from tree_sitter_analyzer.dead_code_analyzer import (
    DeadCodeResult,
    _is_known_entry,
    _is_test_file,
    analyze_dead_code,
    find_transitive_dead_code,
    find_unreferenced_variables,
    find_unused_imports,
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
        source = tmp_path / "main.py"
        source.write_text(
            "def caller():\n"
            "    return callee()\n\n"
            "def callee():\n"
            "    return 1\n\n"
            "def main():\n"
            "    return live_helper()\n\n"
            "def live_helper():\n"
            "    return 2\n"
        )
        return CallGraph(str(tmp_path))

    def test_finds_root_dead_function(self, simple_graph) -> None:
        """Functions never called from outside should be flagged dead."""
        dead = find_transitive_dead_code(simple_graph)
        by_name = {item.function.name: item for item in dead}

        assert by_name["caller"].reason == "no_callers_has_dead_callees"
        assert "main" not in by_name

    def test_propagates_to_callees(self, simple_graph) -> None:
        """Functions only called from dead functions should also be dead."""
        dead = find_transitive_dead_code(simple_graph)
        by_name = {item.function.name: item for item in dead}

        assert by_name["callee"].reason == "unreachable_from_entry"
        assert by_name["caller"].dead_callees == ["callee"]
        assert "live_helper" not in by_name

    def test_excludes_test_files_when_flag_set(self, tmp_path) -> None:
        """When include_test_files=False, test-file functions are excluded."""
        test_file = tmp_path / "test_helper.py"
        test_file.write_text("def helper():\n    return 1\n")

        dead = find_transitive_dead_code(CallGraph(str(tmp_path)))

        assert dead == []

    def test_entry_points_are_not_dead(self, tmp_path) -> None:
        """Known entry-point names should not be flagged."""
        source = tmp_path / "app.py"
        source.write_text("def main():\n    return 1\n")

        dead = find_transitive_dead_code(CallGraph(str(tmp_path)))

        assert dead == []


# ---------------------------------------------------------------------------
# find_unused_imports
# ---------------------------------------------------------------------------


class TestFindUnusedImports:
    def test_detects_unused_import(self, tmp_path) -> None:
        """A file importing `os` but never referencing it should report unused."""
        helper = tmp_path / "helper.py"
        helper.write_text("def unused():\n    return 1\n")
        py = tmp_path / "a.py"
        py.write_text("from helper import unused\n\ndef foo():\n    pass\n")

        unused = find_unused_imports(str(tmp_path))

        assert [(item.file, item.line, item.unused_names) for item in unused] == [
            ("a.py", 1, ["unused"])
        ]

    def test_used_import_not_flagged(self, tmp_path) -> None:
        """An import that IS referenced in code should not be flagged."""
        helper = tmp_path / "helper.py"
        helper.write_text("def used():\n    return 1\n")
        py = tmp_path / "b.py"
        py.write_text("from helper import used\n\ndef foo():\n    return used()\n")

        assert find_unused_imports(str(tmp_path)) == []

    def test_multiple_unused_names(self, tmp_path) -> None:
        """`from x import a, b, c` where only a is used should flag b, c."""
        helper = tmp_path / "helper.py"
        helper.write_text(
            "def used():\n    return 1\n"
            "def unused_a():\n    return 2\n"
            "def unused_b():\n    return 3\n"
        )
        py = tmp_path / "c.py"
        py.write_text(
            "from helper import used, unused_a, unused_b\n\n"
            "def f():\n"
            "    return used()\n"
        )

        unused = find_unused_imports(str(tmp_path))

        assert [(item.file, item.unused_names) for item in unused] == [
            ("c.py", ["unused_a", "unused_b"])
        ]

    def test_unreadable_file_returns_empty(self, tmp_path) -> None:
        """A binary or unreadable file should produce an empty list, not crash."""
        binary = tmp_path / "binary.py"
        binary.write_bytes(b"\x00\xff\x00")

        assert find_unused_imports(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# find_unreferenced_variables
# ---------------------------------------------------------------------------


class TestFindUnreferencedVariables:
    def test_detects_unreferenced_assignment(self, tmp_path) -> None:
        """A module-level variable never referenced should be flagged."""
        py = tmp_path / "vars.py"
        py.write_text("UNUSED = 1\n\ndef foo():\n    return 2\n")

        variables = find_unreferenced_variables(str(tmp_path))

        assert [(item.file, item.name, item.line) for item in variables] == [
            ("vars.py", "UNUSED", 1)
        ]

    def test_referenced_variable_not_flagged(self, tmp_path) -> None:
        """A variable used in a function body should NOT be flagged."""
        py = tmp_path / "vars.py"
        py.write_text("USED = 1\n\ndef foo():\n    return USED\n")

        assert find_unreferenced_variables(str(tmp_path)) == []

    def test_class_attribute_not_flagged_as_unreferenced(self, tmp_path) -> None:
        """Class body assignments are NOT module-level variables."""
        py = tmp_path / "klass.py"
        py.write_text("class Example:\n    value = 1\n")

        assert find_unreferenced_variables(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# analyze_dead_code (top-level)
# ---------------------------------------------------------------------------


class TestAnalyzeDeadCode:
    def test_returns_dead_code_result(self, tmp_path) -> None:
        """Top-level entry should return a DeadCodeResult."""
        py = tmp_path / "simple.py"
        py.write_text("import os\n\ndef dead():\n    pass\n")

        result = analyze_dead_code(str(tmp_path))

        assert isinstance(result, DeadCodeResult)
        assert result.stats["dead_functions"] == 1

    def test_stats_populated(self, tmp_path) -> None:
        """The stats dict should contain file/function counts."""
        py = tmp_path / "simple.py"
        py.write_text("def dead():\n    pass\n")

        result = analyze_dead_code(str(tmp_path))

        assert result.stats == {
            "total_functions": 1,
            "dead_functions": 1,
            "unused_imports": 0,
            "unreferenced_variables": 0,
            "total_call_edges": 0,
        }

    def test_excludes_dirs(self, tmp_path) -> None:
        """node_modules/.git etc. should be excluded from analysis."""
        excluded = tmp_path / "node_modules"
        excluded.mkdir()
        (excluded / "ignored.py").write_text("def dead():\n    pass\n")
        (tmp_path / "kept.py").write_text("def main():\n    return 1\n")

        result = analyze_dead_code(str(tmp_path))

        assert result.stats["total_functions"] == 1
        assert result.dead_functions == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestDeadCodeErrorHandling:
    def test_nonexistent_directory_returns_empty(self) -> None:
        """Passing a path that does not exist should not crash."""
        result = analyze_dead_code("/path/that/does/not/exist")

        assert result.stats["total_functions"] == 0
        assert result.dead_functions == []
        assert result.unused_imports == []
        assert result.unreferenced_variables == []

    def test_binary_file_skipped(self, tmp_path) -> None:
        """Binary files should be silently skipped."""
        binary = tmp_path / "binary.py"
        binary.write_bytes(b"\x00\xff\x00")

        result = analyze_dead_code(str(tmp_path))

        assert result.stats["total_functions"] == 0

    def test_symlink_handled(self, tmp_path) -> None:
        """Symlinked files should not cause infinite loops."""
        target = tmp_path / "target.py"
        target.write_text("def main():\n    return 1\n")
        link = tmp_path / "link.py"
        link.symlink_to(target)

        result = analyze_dead_code(str(tmp_path), max_files=10)

        assert result.stats["total_functions"] >= 1
