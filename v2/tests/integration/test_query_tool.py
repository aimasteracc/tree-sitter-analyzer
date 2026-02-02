"""
Integration tests for MCP query_code tool.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality
"""

from pathlib import Path

import pytest

from tree_sitter_analyzer_v2.mcp.tools.registry import ToolRegistry


@pytest.fixture
def analyze_fixtures_dir():
    """Get path to analyze fixtures directory."""
    return Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"


@pytest.fixture
def registry():
    """Create tool registry with query tool."""
    from tree_sitter_analyzer_v2.mcp.tools.query import QueryTool

    registry = ToolRegistry()
    registry.register(QueryTool())
    return registry


class TestQueryToolBasics:
    """Basic tests for query_code tool."""

    def test_tool_registered(self, registry):
        """Test that query_code tool is registered."""
        tool = registry.get("query_code")
        assert tool is not None
        assert tool.get_name() == "query_code"

    def test_tool_description(self, registry):
        """Test tool has proper description."""
        tool = registry.get("query_code")
        description = tool.get_description()
        assert "query" in description.lower()
        assert "code" in description.lower()

    def test_tool_schema(self, registry):
        """Test tool schema is valid."""
        tool = registry.get("query_code")
        schema = tool.get_schema()

        assert schema["type"] == "object"
        assert "file_path" in schema["properties"]
        assert "element_type" in schema["properties"]
        assert "file_path" in schema["required"]


class TestQueryByElementType:
    """Tests for querying by element type."""

    def test_query_classes(self, registry, analyze_fixtures_dir):
        """Test querying for all classes."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "classes"})

        assert result["success"] is True
        assert "elements" in result
        assert result["count"] > 0
        # Sample.py has DataProcessor class
        assert "DataProcessor" in result["elements"]  # Check TOON/Markdown string

    def test_query_functions(self, registry, analyze_fixtures_dir):
        """Test querying for all functions."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "functions"})

        assert result["success"] is True
        assert result["count"] > 0
        # Sample.py has greet() function
        assert "greet" in result["elements"]  # Check TOON/Markdown string

    def test_query_methods(self, registry, analyze_fixtures_dir):
        """Test querying for all methods."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "methods"})

        assert result["success"] is True
        assert result["count"] > 0
        # DataProcessor class has __init__, process, transform methods
        assert "process" in result["elements"]  # Check TOON/Markdown string

    def test_query_imports(self, registry, analyze_fixtures_dir):
        """Test querying for all imports."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "imports"})

        assert result["success"] is True
        assert result["count"] > 0

    def test_query_all_elements(self, registry, analyze_fixtures_dir):
        """Test querying for all elements (no type filter)."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file)})

        assert result["success"] is True
        assert result["count"] > 0
        # Should include classes, functions, methods, imports


class TestQueryWithFilters:
    """Tests for filtering query results."""

    def test_filter_by_name_exact(self, registry, analyze_fixtures_dir):
        """Test filtering by exact name match."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {
                "file_path": str(python_file),
                "element_type": "classes",
                "filters": {"name": "DataProcessor"},
                "output_format": "raw",  # Use raw format for structure testing
            }
        )

        assert result["success"] is True
        assert len(result["elements"]) == 1
        assert "DataProcessor" in str(result["elements"][0])

    def test_filter_by_name_regex(self, registry, analyze_fixtures_dir):
        """Test filtering by regex pattern."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {
                "file_path": str(python_file),
                "element_type": "methods",
                "filters": {
                    "name": "process.*",  # Matches "process", etc.
                    "use_regex": True,
                },
            }
        )

        assert result["success"] is True
        assert result["count"] > 0
        # Should match "process" method

    def test_filter_by_visibility_java(self, registry, analyze_fixtures_dir):
        """Test filtering by visibility (Java)."""
        tool = registry.get("query_code")
        java_file = analyze_fixtures_dir / "Sample.java"

        result = tool.execute(
            {
                "file_path": str(java_file),
                "element_type": "methods",
                "filters": {"visibility": "public"},
            }
        )

        assert result["success"] is True
        # All methods in Sample.java are public
        assert result["count"] > 0

    def test_filter_multiple_criteria(self, registry, analyze_fixtures_dir):
        """Test filtering with multiple criteria."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {
                "file_path": str(python_file),
                "element_type": "methods",
                "filters": {"name": "process", "class_name": "DataProcessor"},
            }
        )

        assert result["success"] is True
        # Should only return DataProcessor.process method
        assert result["count"] >= 1


class TestQueryResultStructure:
    """Tests for query result structure."""

    def test_result_includes_element_details(self, registry, analyze_fixtures_dir):
        """Test that results include element details."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {
                "file_path": str(python_file),
                "element_type": "classes",
                "filters": {"name": "DataProcessor"},
                "output_format": "raw",  # Use raw format for structure testing
            }
        )

        assert result["success"] is True
        assert len(result["elements"]) == 1

        element = result["elements"][0]
        # Should include name and line information
        assert "name" in element
        assert element["name"] == "DataProcessor"
        assert "line_start" in element or "line" in element

    def test_result_includes_count(self, registry, analyze_fixtures_dir):
        """Test that result includes element count."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "classes"})

        assert result["success"] is True
        assert "count" in result
        assert result["count"] > 0  # Should have at least one class (DataProcessor)

    def test_result_includes_language(self, registry, analyze_fixtures_dir):
        """Test that result includes detected language."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "classes"})

        assert result["success"] is True
        assert "language" in result
        assert result["language"] == "python"


class TestQueryErrorHandling:
    """Tests for error handling."""

    def test_file_not_found(self, registry):
        """Test error when file doesn't exist."""
        tool = registry.get("query_code")

        result = tool.execute({"file_path": "/nonexistent/file.py", "element_type": "classes"})

        assert result["success"] is False
        assert "error" in result

    def test_unsupported_language(self, registry, tmp_path):
        """Test error for unsupported language."""
        tool = registry.get("query_code")

        # Create unsupported file
        unsupported_file = tmp_path / "test.xyz"
        unsupported_file.write_text("some content")

        result = tool.execute({"file_path": str(unsupported_file), "element_type": "classes"})

        assert result["success"] is False
        assert "error" in result

    def test_invalid_element_type(self, registry, analyze_fixtures_dir):
        """Test error for invalid element type."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "invalid_type"})

        # Should either return empty results or error
        assert result["success"] is True
        assert result["count"] == 0


class TestQueryWithOutputFormats:
    """Tests for different output formats."""

    def test_query_default_format_is_toon(self, registry, analyze_fixtures_dir):
        """Test that default output format is TOON."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute({"file_path": str(python_file), "element_type": "classes"})

        assert result["success"] is True
        assert "output_format" in result
        assert result["output_format"] == "toon"
        # Elements should be formatted as TOON string
        if result["count"] > 0:
            assert isinstance(result["elements"], str)

    def test_query_with_toon_format(self, registry, analyze_fixtures_dir):
        """Test query with TOON output format."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {"file_path": str(python_file), "element_type": "classes", "output_format": "toon"}
        )

        assert result["success"] is True
        assert "output_format" in result
        assert result["output_format"] == "toon"
        # Elements should be formatted as TOON string
        if result["count"] > 0:
            assert isinstance(result["elements"], str)

    def test_query_with_markdown_format(self, registry, analyze_fixtures_dir):
        """Test query with Markdown output format."""
        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        result = tool.execute(
            {"file_path": str(python_file), "element_type": "classes", "output_format": "markdown"}
        )

        assert result["success"] is True
        assert result["output_format"] == "markdown"
        # Elements should be formatted as Markdown string
        if result["count"] > 0:
            assert isinstance(result["elements"], str)


class TestQueryPerformance:
    """Performance tests for query tool."""

    def test_query_performance(self, registry, analyze_fixtures_dir):
        """Test that query completes within 100ms."""
        import time

        tool = registry.get("query_code")
        python_file = analyze_fixtures_dir / "sample.py"

        start = time.perf_counter()
        result = tool.execute({"file_path": str(python_file), "element_type": "classes"})
        elapsed = (time.perf_counter() - start) * 1000

        assert result["success"] is True
        # Target: <100ms, but allow 150ms for subprocess overhead
        assert elapsed < 150, f"Query took {elapsed:.2f}ms (expected <150ms)"


class TestQueryLanguageSupport:
    """Tests for multi-language query support."""

    def test_query_java_file(self, registry, analyze_fixtures_dir):
        """Test querying Java file."""
        tool = registry.get("query_code")
        java_file = analyze_fixtures_dir / "Sample.java"

        result = tool.execute({"file_path": str(java_file), "element_type": "classes"})

        assert result["success"] is True
        assert result["language"] == "java"
        assert result["count"] > 0

    def test_query_typescript_file(self, registry, analyze_fixtures_dir):
        """Test querying TypeScript file."""
        tool = registry.get("query_code")
        ts_file = analyze_fixtures_dir / "sample.ts"

        result = tool.execute({"file_path": str(ts_file), "element_type": "classes"})

        assert result["success"] is True
        assert result["language"] in ["typescript", "javascript"]
        assert result["count"] > 0
