"""
Integration tests for MCP search tools (find_files and search_content).

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality
"""

import pytest

from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry


@pytest.fixture
def search_fixtures_dir(tmp_path):
    """Create a temporary directory with search fixtures."""
    # Create directory structure
    fixtures_dir = tmp_path / "search_test"
    fixtures_dir.mkdir()

    # Create sample Python file
    python_file = fixtures_dir / "sample.py"
    python_file.write_text("""
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b
""")

    # Create sample TypeScript file
    ts_file = fixtures_dir / "sample.ts"
    ts_file.write_text("""
interface User {
    name: string;
    age: number;
}

class UserService {
    getUser(id: number): User {
        return { name: "John", age: 30 };
    }
}
""")

    # Create subdirectory
    subdir = fixtures_dir / "utils"
    subdir.mkdir()

    # Create Java file in subdirectory
    java_file = subdir / "Helper.java"
    java_file.write_text("""
public class Helper {
    public static void main(String[] args) {
        System.out.println("Helper");
    }
}
""")

    return fixtures_dir


@pytest.fixture
def registry():
    """Create tool registry with search tools."""
    from tree_sitter_analyzer_v2.mcp.tools.search import FindFilesTool, SearchContentTool

    registry = ToolRegistry()
    registry.register(FindFilesTool())
    registry.register(SearchContentTool())
    return registry


class TestFindFilesTool:
    """Tests for find_files MCP tool."""

    def test_tool_registered(self, registry):
        """Test that find_files tool is registered."""
        tool = registry.get("find_files")
        assert tool is not None
        assert tool.get_name() == "find_files"

    def test_tool_description(self, registry):
        """Test tool has proper description."""
        tool = registry.get("find_files")
        description = tool.get_description()
        assert "file" in description.lower()
        assert "search" in description.lower() or "find" in description.lower()

    def test_tool_schema(self, registry):
        """Test tool schema is valid."""
        tool = registry.get("find_files")
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "root_dir" in schema["properties"]
        assert "pattern" in schema["properties"]
        assert "root_dir" in schema["required"]
        assert "pattern" in schema["required"]

    def test_find_python_files(self, registry, search_fixtures_dir):
        """Test finding Python files."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*.py"})

        assert result["success"] is True
        assert "files" in result
        assert len(result["files"]) == 1
        assert result["files"][0].endswith("sample.py")

    def test_find_typescript_files(self, registry, search_fixtures_dir):
        """Test finding TypeScript files."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*.ts"})

        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0].endswith("sample.ts")

    def test_find_all_files_recursively(self, registry, search_fixtures_dir):
        """Test finding all files recursively."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*"})

        assert result["success"] is True
        assert len(result["files"]) >= 3  # Python, TypeScript, Java

    def test_find_java_files_with_type_filter(self, registry, search_fixtures_dir):
        """Test finding Java files with file type filter."""
        tool = registry.get("find_files")

        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "*", "file_type": "java"}
        )

        assert result["success"] is True
        assert len(result["files"]) == 1
        assert result["files"][0].endswith("Helper.java")

    def test_nonexistent_directory(self, registry):
        """Test error handling for non-existent directory."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": "/nonexistent/directory", "pattern": "*.py"})

        assert result["success"] is False
        assert "error" in result

    def test_no_matches(self, registry, search_fixtures_dir):
        """Test when no files match the pattern."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*.nonexistent"})

        assert result["success"] is True
        assert result["files"] == []

    def test_result_count(self, registry, search_fixtures_dir):
        """Test that result includes file count."""
        tool = registry.get("find_files")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*.py"})

        assert result["success"] is True
        assert "count" in result
        assert result["count"] == len(result["files"])


class TestSearchContentTool:
    """Tests for search_content MCP tool."""

    def test_tool_registered(self, registry):
        """Test that search_content tool is registered."""
        tool = registry.get("search_content")
        assert tool is not None
        assert tool.get_name() == "search_content"

    def test_tool_description(self, registry):
        """Test tool has proper description."""
        tool = registry.get("search_content")
        description = tool.get_description()
        assert "content" in description.lower()
        assert "search" in description.lower()

    def test_tool_schema(self, registry):
        """Test tool schema is valid."""
        tool = registry.get("search_content")
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "root_dir" in schema["properties"]
        assert "pattern" in schema["properties"]
        assert "root_dir" in schema["required"]
        assert "pattern" in schema["required"]

    def test_search_class_keyword(self, registry, search_fixtures_dir):
        """Test searching for 'class' keyword."""
        tool = registry.get("search_content")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "class"})

        assert result["success"] is True
        assert "matches" in result
        assert len(result["matches"]) >= 2  # Calculator, UserService, Helper

    def test_search_with_regex(self, registry, search_fixtures_dir):
        """Test searching with regex pattern."""
        tool = registry.get("search_content")

        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "class \\w+", "use_regex": True}
        )

        assert result["success"] is True
        assert len(result["matches"]) >= 2

    def test_search_with_file_type_filter(self, registry, search_fixtures_dir):
        """Test searching with file type filter."""
        tool = registry.get("search_content")

        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "class", "file_type": "py"}
        )

        assert result["success"] is True
        # Should only find Calculator class in Python file
        assert all("sample.py" in match["file"] for match in result["matches"])

    def test_case_insensitive_search(self, registry, search_fixtures_dir):
        """Test case-insensitive search."""
        tool = registry.get("search_content")

        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "CLASS", "case_sensitive": False}
        )

        assert result["success"] is True
        assert len(result["matches"]) >= 2

    def test_case_sensitive_search(self, registry, search_fixtures_dir):
        """Test case-sensitive search."""
        tool = registry.get("search_content")

        # Search for uppercase CLASS (should not match)
        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "CLASS", "case_sensitive": True}
        )

        assert result["success"] is True
        assert len(result["matches"]) == 0  # No uppercase CLASS

    def test_search_result_structure(self, registry, search_fixtures_dir):
        """Test that search results have proper structure."""
        tool = registry.get("search_content")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "Calculator"})

        assert result["success"] is True
        assert len(result["matches"]) > 0

        # Check first match structure
        match = result["matches"][0]
        assert "file" in match
        assert "line_number" in match
        assert "line" in match
        assert isinstance(match["line_number"], int)

    def test_no_matches_found(self, registry, search_fixtures_dir):
        """Test when no matches are found."""
        tool = registry.get("search_content")

        result = tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "nonexistent_pattern_xyz"}
        )

        assert result["success"] is True
        assert result["matches"] == []

    def test_nonexistent_directory(self, registry):
        """Test error handling for non-existent directory."""
        tool = registry.get("search_content")

        result = tool.execute({"root_dir": "/nonexistent/directory", "pattern": "class"})

        assert result["success"] is False
        assert "error" in result

    def test_result_count(self, registry, search_fixtures_dir):
        """Test that result includes match count."""
        tool = registry.get("search_content")

        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "class"})

        assert result["success"] is True
        assert "count" in result
        assert result["count"] == len(result["matches"])


class TestSearchToolsPerformance:
    """Performance tests for search tools."""

    def test_find_files_performance(self, registry, search_fixtures_dir):
        """Test that find_files completes within reasonable time."""
        import time

        tool = registry.get("find_files")

        start = time.perf_counter()
        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*"})
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000
        assert result["success"] is True
        # 500ms threshold to avoid flaky failures in CI / full test suite runs
        assert elapsed_ms < 500, f"find_files took {elapsed_ms:.2f}ms (expected <500ms)"

    def test_search_content_performance(self, registry, search_fixtures_dir):
        """Test that search_content completes within reasonable time."""
        import time

        tool = registry.get("search_content")

        start = time.perf_counter()
        result = tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "class"})
        end = time.perf_counter()

        elapsed_ms = (end - start) * 1000
        assert result["success"] is True
        # 500ms threshold to avoid flaky failures in CI / full test suite runs
        assert elapsed_ms < 500, f"search_content took {elapsed_ms:.2f}ms (expected <500ms)"


class TestSearchToolsIntegration:
    """Integration tests combining both search tools."""

    def test_find_then_search(self, registry, search_fixtures_dir):
        """Test finding files then searching their content."""
        find_tool = registry.get("find_files")
        search_tool = registry.get("search_content")

        # First, find all Python files
        find_result = find_tool.execute({"root_dir": str(search_fixtures_dir), "pattern": "*.py"})

        assert find_result["success"] is True
        assert len(find_result["files"]) > 0

        # Then search for content in those files
        search_result = search_tool.execute(
            {"root_dir": str(search_fixtures_dir), "pattern": "Calculator", "file_type": "py"}
        )

        assert search_result["success"] is True
        assert len(search_result["matches"]) > 0

    def test_tool_schemas_complete(self, registry):
        """Test that both tools have complete schemas."""
        find_tool = registry.get("find_files")
        search_tool = registry.get("search_content")

        find_schema = find_tool.get_schema()
        search_schema = search_tool.get_schema()

        # Both should have required fields
        assert "properties" in find_schema
        assert "required" in find_schema
        assert "properties" in search_schema
        assert "required" in search_schema
