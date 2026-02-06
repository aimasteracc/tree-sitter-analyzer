"""
Integration tests for find_and_grep MCP tool.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

This is T7.3: find_and_grep Tool
"""

import pytest


class TestFindAndGrepTool:
    """Tests for FindAndGrepTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool can be initialized."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        assert tool is not None

    def test_tool_definition(self):
        """Test tool has proper definition."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()
        definition = tool.get_tool_definition()

        assert "name" in definition
        assert definition["name"] == "find_and_grep"
        assert "description" in definition
        assert "inputSchema" in definition

    def test_find_files_only(self, tmp_path):
        """Test finding files without content search."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create test files
        (tmp_path / "test1.py").write_text("print('hello')")
        (tmp_path / "test2.py").write_text("print('world')")
        (tmp_path / "other.txt").write_text("some text")

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(tmp_path)], "pattern": "*.py"})

        assert result["success"] is True
        assert "files" in result
        assert len(result["files"]) == 2

    def test_find_and_grep_combined(self, tmp_path):
        """Test combined file finding and content search."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create test files
        (tmp_path / "test1.py").write_text("def hello():\n    print('hello')")
        (tmp_path / "test2.py").write_text("def world():\n    print('world')")
        (tmp_path / "test3.py").write_text("x = 42")

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(tmp_path)], "pattern": "*.py", "query": "def "})

        assert result["success"] is True
        assert "matches" in result
        # Should find matches in test1.py and test2.py (have "def")
        assert len(result["matches"]) >= 2

    def test_extension_filter(self, tmp_path):
        """Test filtering by file extension."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create test files
        (tmp_path / "file.py").write_text("python")
        (tmp_path / "file.js").write_text("javascript")
        (tmp_path / "file.txt").write_text("text")

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(tmp_path)], "extensions": ["py"]})

        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0].endswith(".py")

    def test_case_insensitive_search(self, tmp_path):
        """Test case-insensitive content search."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        (tmp_path / "test.py").write_text("CLASS MyClass:\n    pass")

        tool = FindAndGrepTool()

        result = tool.execute(
            {"roots": [str(tmp_path)], "pattern": "*.py", "query": "class", "case_sensitive": False}
        )

        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_regex_search(self, tmp_path):
        """Test regex pattern in content search."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        (tmp_path / "test.py").write_text("function_1\nfunction_2\nvar_name")

        tool = FindAndGrepTool()

        result = tool.execute(
            {
                "roots": [str(tmp_path)],
                "pattern": "*.py",
                "query": "function_[0-9]",
                "is_regex": True,
            }
        )

        assert result["success"] is True
        assert len(result["matches"]) >= 1

    def test_multiple_roots(self, tmp_path):
        """Test searching in multiple root directories."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        # Create subdirectories
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "file1.py").write_text("content1")
        (dir2 / "file2.py").write_text("content2")

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(dir1), str(dir2)], "pattern": "*.py"})

        assert result["success"] is True
        assert len(result["files"]) == 2

    def test_no_results(self, tmp_path):
        """Test when no files match."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        (tmp_path / "file.txt").write_text("text")

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(tmp_path)], "pattern": "*.py"})

        assert result["success"] is True
        assert len(result["files"]) == 0

    def test_output_format_toon(self, tmp_path):
        """Test TOON output format."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        (tmp_path / "test.py").write_text("hello")

        tool = FindAndGrepTool()

        result = tool.execute(
            {"roots": [str(tmp_path)], "pattern": "*.py", "output_format": "toon"}
        )

        assert result["success"] is True
        assert result["output_format"] == "toon"

    def test_nonexistent_directory(self):
        """Test error handling for nonexistent directory."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()

        result = tool.execute({"roots": ["/nonexistent/path"], "pattern": "*.py"})

        assert result["success"] is False
        assert "error" in result


@pytest.fixture
def sample_project(tmp_path):
    """Create a sample project structure for testing."""
    # Source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("""
def main():
    print("Hello, World!")

if __name__ == "__main__":
    main()
""")
    (src / "utils.py").write_text("""
def helper_function(x):
    return x * 2

class UtilityClass:
    pass
""")

    # Test files
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("""
def test_main():
    assert True
""")

    return tmp_path


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_find_all_python_files(self, sample_project):
        """Test finding all Python files in a project."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()

        result = tool.execute({"roots": [str(sample_project)], "pattern": "*.py"})

        assert result["success"] is True
        assert len(result["files"]) == 3

    def test_search_for_class_definitions(self, sample_project):
        """Test searching for class definitions."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()

        result = tool.execute(
            {
                "roots": [str(sample_project)],
                "pattern": "*.py",
                "query": "class ",
                "case_sensitive": True,
            }
        )

        assert result["success"] is True
        # Should find UtilityClass in utils.py
        assert len(result["matches"]) >= 1

    def test_search_test_files_only(self, sample_project):
        """Test searching only in test files."""
        from tree_sitter_analyzer_v2.mcp.tools.find_and_grep import FindAndGrepTool

        tool = FindAndGrepTool()

        result = tool.execute(
            {"roots": [str(sample_project / "tests")], "pattern": "test_*.py", "query": "def test_"}
        )

        assert result["success"] is True
        assert len(result["matches"]) >= 1
