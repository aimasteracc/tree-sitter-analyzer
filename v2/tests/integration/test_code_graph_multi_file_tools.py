"""
Integration tests for Code Graph MCP Tool with multi-file analysis (E2).

Tests the AnalyzeCodeGraphTool with directory parameter:
- Directory analysis
- Pattern matching
- Exclusion patterns
- Error handling
"""

import tempfile
from pathlib import Path

from tree_sitter_analyzer_v2.mcp.tools.code_graph import AnalyzeCodeGraphTool


class TestAnalyzeCodeGraphToolMultiFile:
    """Tests for AnalyzeCodeGraphTool with multi-file support."""

    def test_tool_schema_includes_directory_parameter(self):
        """Test that tool schema includes directory and related parameters."""
        tool = AnalyzeCodeGraphTool()
        schema = tool.get_schema()

        # Verify new parameters exist
        assert "directory" in schema["properties"]
        assert "pattern" in schema["properties"]
        assert "exclude_patterns" in schema["properties"]
        assert "max_files" in schema["properties"]

        # Verify descriptions exist and are non-empty
        assert len(schema["properties"]["directory"]["description"]) > 0
        assert len(schema["properties"]["pattern"]["description"]) > 0

    def test_analyze_directory_basic(self):
        """Test analyzing a directory with multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create multiple Python files
            (tmppath / "module1.py").write_text("""
def func1():
    return 1

def func2():
    return func1()
""")

            (tmppath / "module2.py").write_text("""
class MyClass:
    def method1(self):
        return 2

def func3():
    return MyClass().method1()
""")

            # Execute tool
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath)})

            # Verify success
            assert result["success"] is True
            assert "directory" in result
            assert result["directory"] == str(tmppath)

            # Verify statistics
            assert "statistics" in result
            assert result["statistics"]["modules"] == 2
            assert result["statistics"]["classes"] == 1
            assert result["statistics"]["functions"] >= 3

            # Verify files_analyzed metadata
            assert "files_analyzed" in result
            assert result["files_analyzed"] == 2

    def test_analyze_directory_with_pattern(self):
        """Test analyzing directory with custom pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create files with different names
            (tmppath / "app.py").write_text("def app_func(): pass")
            (tmppath / "test.py").write_text("def test_func(): pass")
            (tmppath / "util.py").write_text("def util_func(): pass")

            # Execute tool with pattern for only app*.py
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath), "pattern": "app*.py"})

            # Verify success
            assert result["success"] is True

            # Should only analyze app.py (1 module)
            assert result["statistics"]["modules"] == 1
            assert result["files_analyzed"] == 1

            # Verify pattern is in result
            assert "pattern" in result
            assert result["pattern"] == "app*.py"

    def test_analyze_directory_with_exclusions(self):
        """Test analyzing directory with exclusion patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create files
            (tmppath / "app.py").write_text("def app_func(): pass")
            (tmppath / "test_app.py").write_text("def test_func(): pass")
            (tmppath / "utils.py").write_text("def util_func(): pass")

            # Execute tool excluding test files
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath), "exclude_patterns": ["**/test_*.py"]})

            # Verify success
            assert result["success"] is True

            # Should exclude test_app.py (2 modules instead of 3)
            assert result["statistics"]["modules"] == 2
            assert result["files_analyzed"] == 2

            # Verify exclusion patterns in result
            assert "exclude_patterns" in result
            assert result["exclude_patterns"] == ["**/test_*.py"]

    def test_analyze_directory_with_max_files(self):
        """Test analyzing directory with max_files limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 5 files
            for i in range(5):
                (tmppath / f"file{i}.py").write_text(f"def func{i}(): pass")

            # Execute tool with max_files=3
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath), "max_files": 3})

            # Verify success
            assert result["success"] is True

            # Should only analyze 3 files
            assert result["files_analyzed"] == 3
            assert result["statistics"]["modules"] == 3

    def test_analyze_directory_empty(self):
        """Test analyzing empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Execute tool on empty directory
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": tmpdir})

            # Verify success (empty result)
            assert result["success"] is True
            assert result["files_analyzed"] == 0
            assert result["statistics"]["modules"] == 0

    def test_analyze_directory_nonexistent(self):
        """Test error handling for nonexistent directory."""
        tool = AnalyzeCodeGraphTool()
        result = tool.execute({"directory": "/nonexistent/directory"})

        # Verify error
        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_analyze_both_file_and_directory_error(self):
        """Test error when both file_path and directory are specified."""
        tool = AnalyzeCodeGraphTool()
        result = tool.execute({"file_path": "test.py", "directory": "/some/dir"})

        # Verify error
        assert result["success"] is False
        assert "error" in result
        assert "both" in result["error"].lower()

    def test_analyze_neither_file_nor_directory_error(self):
        """Test error when neither file_path nor directory is specified."""
        tool = AnalyzeCodeGraphTool()
        result = tool.execute({})

        # Verify error
        assert result["success"] is False
        assert "error" in result
        assert "must specify" in result["error"].lower()

    def test_analyze_directory_with_subdirectories(self):
        """Test analyzing directory with nested subdirectories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create nested structure
            (tmppath / "root.py").write_text("def root_func(): pass")

            subdir = tmppath / "subdir"
            subdir.mkdir()
            (subdir / "sub.py").write_text("def sub_func(): pass")

            nested = subdir / "nested"
            nested.mkdir()
            (nested / "nested.py").write_text("def nested_func(): pass")

            # Execute tool with recursive pattern
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath), "pattern": "**/*.py"})

            # Verify all files were found
            assert result["success"] is True
            assert result["files_analyzed"] == 3
            assert result["statistics"]["modules"] == 3

    def test_analyze_directory_with_detail_levels(self):
        """Test directory analysis with different detail levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            (tmppath / "test.py").write_text("""
def func(a: int, b: str) -> bool:
    return True
""")

            tool = AnalyzeCodeGraphTool()

            # Summary mode
            summary_result = tool.execute({"directory": str(tmppath), "detail_level": "summary"})
            assert summary_result["success"] is True

            # Detailed mode
            detailed_result = tool.execute({"directory": str(tmppath), "detail_level": "detailed"})
            assert detailed_result["success"] is True

            # Detailed should have more info
            assert len(detailed_result["structure"]) >= len(summary_result["structure"])

    def test_analyze_directory_preserves_structure_format(self):
        """Test that directory analysis returns TOON formatted structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            (tmppath / "test.py").write_text("""
def helper():
    return 42

def main():
    return helper()
""")

            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath)})

            # Verify TOON format
            assert result["success"] is True
            assert "structure" in result
            assert result["format"] == "toon"
            assert "MODULE" in result["structure"] or "TOON" in result["structure"]

    def test_analyze_directory_large_project(self):
        """Test directory analysis with many files (performance check)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create 15 files
            for i in range(15):
                (tmppath / f"module{i}.py").write_text(f"""
def func{i}_1():
    return {i}

def func{i}_2():
    return func{i}_1()
""")

            # Execute tool
            tool = AnalyzeCodeGraphTool()
            result = tool.execute({"directory": str(tmppath)})

            # Verify all files were analyzed
            assert result["success"] is True
            assert result["files_analyzed"] == 15
            assert result["statistics"]["modules"] == 15

            # Should have 2 functions per module = 30 total
            assert result["statistics"]["functions"] == 30
