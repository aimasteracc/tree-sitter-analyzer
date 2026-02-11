"""
Unit tests for Code Graph multi-file analysis (E2 Enhancement).

Tests the build_from_directory() functionality including:
- Directory analysis with multiple files
- Glob pattern matching
- Exclusion patterns
- Max files limit
- Parallel processing
- Graph merging
"""

import tempfile
from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.graph.builder import CodeGraphBuilder


class TestCodeGraphMultiFile:
    """Tests for multi-file code graph analysis."""

    def test_build_from_directory_basic(self):
        """Test basic directory analysis with multiple Python files."""
        # Create temp directory with Python files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create file1.py
            (tmppath / "file1.py").write_text("""
def func1():
    return 1

def func2():
    return func1()
""")

            # Create file2.py
            (tmppath / "file2.py").write_text("""
def func3():
    return 3

def func4():
    return func3()
""")

            # Build graph from directory
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            # Verify graph contains nodes from both files
            assert graph.number_of_nodes() > 0

            # Check for modules
            module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            assert len(module_nodes) == 2  # file1 and file2

            # Check for functions
            function_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"]
            assert len(function_nodes) == 4  # func1, func2, func3, func4

            # Verify metadata
            assert graph.graph["files_analyzed"] == 2
            assert "directory" in graph.graph

    def test_build_from_directory_with_subdirectories(self):
        """Test directory analysis with subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create subdirectory
            subdir = tmppath / "subdir"
            subdir.mkdir()

            # Create files in different directories
            (tmppath / "root.py").write_text("def root_func(): pass")
            (subdir / "sub.py").write_text("def sub_func(): pass")

            # Build graph with recursive pattern
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath), pattern="**/*.py")

            # Verify both files were analyzed
            module_nodes = [n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            assert len(module_nodes) == 2

    def test_build_from_directory_with_exclusion_patterns(self):
        """Test directory analysis with exclusion patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create various files
            (tmppath / "app.py").write_text("def app_func(): pass")
            (tmppath / "test_app.py").write_text("def test_func(): pass")
            (tmppath / "utils.py").write_text("def util_func(): pass")

            # Build graph excluding test files
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath), exclude_patterns=["**/test_*.py"])

            # Verify test file was excluded
            module_names = [d["name"] for _, d in graph.nodes(data=True) if d["type"] == "MODULE"]

            assert "app" in module_names
            assert "utils" in module_names
            assert "test_app" not in module_names

    def test_build_from_directory_with_max_files(self):
        """Test directory analysis with max_files limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 5 files
            for i in range(5):
                (tmppath / f"file{i}.py").write_text(f"def func{i}(): pass")

            # Build graph with max_files=3
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath), max_files=3)

            # Verify only 3 files were analyzed
            assert graph.graph["files_analyzed"] == 3

    def test_build_from_directory_empty_directory(self):
        """Test directory analysis with no Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create non-Python file
            (tmppath / "readme.txt").write_text("Not a Python file")

            # Build graph from empty directory
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            # Verify empty graph
            assert graph.number_of_nodes() == 0
            assert graph.graph["files_analyzed"] == 0

    def test_build_from_directory_nonexistent_directory(self):
        """Test error handling for nonexistent directory."""
        builder = CodeGraphBuilder()

        with pytest.raises(FileNotFoundError):
            builder.build_from_directory("/nonexistent/directory")

    def test_build_from_directory_file_instead_of_directory(self):
        """Test error handling when passing a file instead of directory."""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def func(): pass")
            temp_path = f.name

        try:
            builder = CodeGraphBuilder()

            with pytest.raises(ValueError, match="Not a directory"):
                builder.build_from_directory(temp_path)

        finally:
            Path(temp_path).unlink()

    def test_build_from_directory_with_errors(self):
        """Test directory analysis handles files with syntax errors gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create valid file
            (tmppath / "valid.py").write_text("def valid_func(): pass")

            # Create invalid file (syntax error)
            (tmppath / "invalid.py").write_text("def invalid_func(: pass")

            # Build graph - should not crash
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            # Should have at least the valid file
            # (invalid file should be skipped)
            assert graph.number_of_nodes() > 0

    def test_build_from_directory_preserves_call_relationships(self):
        """Test that call relationships are preserved across files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create file with function calls
            (tmppath / "caller.py").write_text("""
def helper():
    return 42

def main():
    return helper()
""")

            # Build graph
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            # Verify CALLS edges exist
            calls_edges = [e for e in graph.edges(data=True) if e[2]["type"] == "CALLS"]
            assert len(calls_edges) > 0

    def test_build_from_directory_graph_metadata(self):
        """Test that graph metadata is correctly set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            (tmppath / "test.py").write_text("def test(): pass")

            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(
                str(tmppath), pattern="**/*.py", exclude_patterns=["**/ignore_*.py"]
            )

            # Verify metadata
            assert "files_analyzed" in graph.graph
            assert "directory" in graph.graph
            assert "pattern" in graph.graph
            assert "exclude_patterns" in graph.graph
            assert graph.graph["pattern"] == "**/*.py"
            assert graph.graph["exclude_patterns"] == ["**/ignore_*.py"]

    def test_build_from_directory_large_project(self):
        """Test directory analysis with many files (performance test)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 20 files
            for i in range(20):
                (tmppath / f"module{i}.py").write_text(f"""
def func{i}_1():
    return {i}

def func{i}_2():
    return func{i}_1()

class Class{i}:
    def method{i}(self):
        return func{i}_2()
""")

            # Build graph
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath))

            # Verify all files were processed
            assert graph.graph["files_analyzed"] == 20

            # Verify node counts
            modules = len([n for n, d in graph.nodes(data=True) if d["type"] == "MODULE"])
            classes = len([n for n, d in graph.nodes(data=True) if d["type"] == "CLASS"])
            functions = len([n for n, d in graph.nodes(data=True) if d["type"] == "FUNCTION"])

            assert modules == 20
            assert classes == 20
            # Each file has 2 functions + 1 method = 3 per file
            assert functions == 60  # 20 files * 3 functions

    def test_build_from_directory_custom_pattern(self):
        """Test directory analysis with custom glob pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create files
            (tmppath / "app.py").write_text("def app(): pass")
            (tmppath / "test.py").write_text("def test(): pass")
            (tmppath / "script.py").write_text("def script(): pass")

            # Build graph with custom pattern (only app*.py)
            builder = CodeGraphBuilder()
            graph = builder.build_from_directory(str(tmppath), pattern="app*.py")

            # Verify only app.py was analyzed
            module_nodes = [d["name"] for n, d in graph.nodes(data=True) if d["type"] == "MODULE"]
            assert "app" in module_nodes
            assert "test" not in module_nodes
            assert "script" not in module_nodes
