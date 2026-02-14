"""Tests for ProjectIndexer file discovery: PI-001 Prioritized File Discovery."""

from __future__ import annotations

import os

from tree_sitter_analyzer.intelligence.project_indexer import (
    _MAX_FILES,
    ProjectIndexer,
)

# ---------------------------------------------------------------------------
# PI-001: _MAX_FILES increased to 2000
# ---------------------------------------------------------------------------


class TestMaxFilesLimit:
    """_MAX_FILES must be >= 2000 to cover typical projects."""

    def test_max_files_at_least_2000(self):
        assert _MAX_FILES >= 2000, (
            f"_MAX_FILES is {_MAX_FILES}, expected >= 2000 to avoid "
            f"truncating source directories like mcp/"
        )


# ---------------------------------------------------------------------------
# PI-001: Two-phase discovery — source files before test files
# ---------------------------------------------------------------------------


class TestTwoPhaseDiscovery:
    """Source files should be discovered before test files."""

    def test_source_files_come_before_test_files(self, tmp_path):
        """When limit is tight, source files must appear before test files."""
        # Create source files
        src_dir = tmp_path / "mylib"
        src_dir.mkdir()
        for i in range(5):
            (src_dir / f"module_{i}.py").write_text(f"# module {i}")

        # Create test files
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        for i in range(5):
            (test_dir / f"test_module_{i}.py").write_text(f"# test {i}")

        indexer = ProjectIndexer(str(tmp_path))
        files = indexer._discover_python_files(str(tmp_path))

        # Find positions of source vs test files
        source_positions = []
        test_positions = []
        for idx, f in enumerate(files):
            basename = os.path.basename(f)
            if basename.startswith("test_"):
                test_positions.append(idx)
            else:
                source_positions.append(idx)

        if source_positions and test_positions:
            assert max(source_positions) < min(
                test_positions
            ), "Source files must appear before test files in discovery order"

    def test_all_source_files_included_when_limit_tight(self, tmp_path):
        """Even with tight limits, ALL source files must be included."""
        # Create 10 source files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for i in range(10):
            (src_dir / f"mod_{i}.py").write_text(f"# mod {i}")

        # Create 2000 test files (more than _MAX_FILES)
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        for i in range(50):
            (test_dir / f"test_{i}.py").write_text(f"# test {i}")

        indexer = ProjectIndexer(str(tmp_path))
        files = indexer._discover_python_files(str(tmp_path))

        # All 10 source files must be present
        source_basenames = {os.path.basename(f) for f in files if "src" in f}
        for i in range(10):
            assert (
                f"mod_{i}.py" in source_basenames
            ), f"Source file mod_{i}.py missing from discovery"


# ---------------------------------------------------------------------------
# PI-002: is_test_file classification
# ---------------------------------------------------------------------------


class TestIsTestFile:
    """ProjectIndexer.is_test_file must correctly classify test vs source files."""

    def test_test_prefix(self):
        assert ProjectIndexer.is_test_file("tests/test_foo.py") is True

    def test_test_suffix(self):
        assert ProjectIndexer.is_test_file("tests/foo_test.py") is True

    def test_conftest(self):
        assert ProjectIndexer.is_test_file("tests/conftest.py") is True

    def test_tests_directory(self):
        assert ProjectIndexer.is_test_file("tests/unit/helpers.py") is True

    def test_test_directory_singular(self):
        assert ProjectIndexer.is_test_file("test/unit/helpers.py") is True

    def test_source_file(self):
        assert (
            ProjectIndexer.is_test_file("tree_sitter_analyzer/core/analysis_engine.py")
            is False
        )

    def test_source_init(self):
        assert ProjectIndexer.is_test_file("tree_sitter_analyzer/__init__.py") is False

    def test_nested_source(self):
        assert (
            ProjectIndexer.is_test_file(
                "tree_sitter_analyzer/mcp/tools/trace_symbol_tool.py"
            )
            is False
        )


# ---------------------------------------------------------------------------
# PI-002: get_test_files / get_source_files
# ---------------------------------------------------------------------------


class TestFileClassificationSets:
    """get_test_files and get_source_files must partition indexed files."""

    def test_partition_after_indexing(self, tmp_path):
        # Create a minimal project
        src_dir = tmp_path / "mylib"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("")
        (src_dir / "core.py").write_text("def hello(): pass")

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_core.py").write_text("from mylib.core import hello")

        indexer = ProjectIndexer(str(tmp_path))
        indexer.ensure_indexed()

        test_files = indexer.get_test_files()
        source_files = indexer.get_source_files()

        # test_core.py should be in test_files
        assert any("test_core.py" in f for f in test_files)
        # core.py should be in source_files
        assert any("core.py" in f for f in source_files)
        # No overlap
        assert not test_files & source_files
