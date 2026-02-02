"""
Integration tests for AnalyzeTool.

Tests the analyze_code_structure MCP tool that analyzes code files
and returns structured information in TOON or Markdown format.
"""

from pathlib import Path

from tree_sitter_analyzer_v2.mcp.tools.analyze import AnalyzeTool

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"


class TestAnalyzeTool:
    """Test suite for AnalyzeTool."""

    def setup_method(self):
        """Set up test fixture."""
        self.tool = AnalyzeTool()

    def test_get_name(self):
        """Test tool name is correct."""
        assert self.tool.get_name() == "analyze_code_structure"

    def test_get_description(self):
        """Test tool description exists and is meaningful."""
        description = self.tool.get_description()
        assert isinstance(description, str)
        assert len(description) > 20
        assert "analyze" in description.lower() or "code" in description.lower()

    def test_get_schema(self):
        """Test tool schema is valid JSON Schema."""
        schema = self.tool.get_schema()

        # Should be a valid JSON Schema object
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"

        # Should have required properties
        properties = schema.get("properties", {})
        assert "file_path" in properties
        assert "output_format" in properties

        # file_path should be required string
        assert properties["file_path"]["type"] == "string"

        # output_format should be optional with enum
        assert properties["output_format"]["type"] == "string"
        assert "enum" in properties["output_format"]
        assert set(properties["output_format"]["enum"]) == {"toon", "markdown"}

    def test_analyze_python_file_toon_format(self):
        """Test analyzing Python file with TOON format output."""
        file_path = str(FIXTURES_DIR / "sample.py")

        result = self.tool.execute({"file_path": file_path, "output_format": "toon"})

        # Check result structure
        assert result["success"] is True
        assert result["language"] == "python"
        assert result["output_format"] == "toon"
        assert result["error"] is None

        # Check TOON output contains expected elements
        data = result["data"]
        assert isinstance(data, str)
        assert len(data) > 0

        # TOON format should contain function and class info
        assert "greet" in data or "DataProcessor" in data

    def test_analyze_python_file_markdown_format(self):
        """Test analyzing Python file with Markdown format output."""
        file_path = str(FIXTURES_DIR / "sample.py")

        result = self.tool.execute({"file_path": file_path, "output_format": "markdown"})

        # Check result structure
        assert result["success"] is True
        assert result["language"] == "python"
        assert result["output_format"] == "markdown"
        assert result["error"] is None

        # Check Markdown output
        data = result["data"]
        assert isinstance(data, str)
        assert len(data) > 0

        # Markdown should have headings and content
        assert "#" in data  # Markdown headings
        assert "greet" in data or "DataProcessor" in data

    def test_analyze_typescript_file(self):
        """Test analyzing TypeScript file."""
        file_path = str(FIXTURES_DIR / "sample.ts")

        result = self.tool.execute({"file_path": file_path, "output_format": "toon"})

        assert result["success"] is True
        assert result["language"] == "typescript"
        assert result["output_format"] == "toon"
        assert result["error"] is None

        # Should contain TypeScript elements
        data = result["data"]
        assert "UserService" in data or "User" in data or "formatUser" in data

    def test_analyze_java_file(self):
        """Test analyzing Java file."""
        file_path = str(FIXTURES_DIR / "Sample.java")

        result = self.tool.execute({"file_path": file_path, "output_format": "toon"})

        assert result["success"] is True
        assert result["language"] == "java"
        assert result["output_format"] == "toon"
        assert result["error"] is None

        # Should contain Java elements
        data = result["data"]
        assert "Sample" in data or "getName" in data

    def test_analyze_default_format_is_toon(self):
        """Test that default output format is TOON."""
        file_path = str(FIXTURES_DIR / "sample.py")

        # Don't specify output_format
        result = self.tool.execute({"file_path": file_path})

        assert result["success"] is True
        assert result["output_format"] == "toon"

    def test_error_file_not_found(self):
        """Test error when file does not exist."""
        result = self.tool.execute({"file_path": "nonexistent_file.py", "output_format": "toon"})

        assert result["success"] is False
        assert result["error"] is not None
        assert "not found" in result["error"].lower() or "does not exist" in result["error"].lower()

    def test_error_unsupported_language(self):
        """Test error when language is not supported."""
        # Create a temporary file with unsupported extension
        temp_file = FIXTURES_DIR / "test.xyz"
        try:
            temp_file.write_text("some content")

            result = self.tool.execute({"file_path": str(temp_file), "output_format": "toon"})

            assert result["success"] is False
            assert result["error"] is not None
            assert "unsupported" in result["error"].lower() or "language" in result["error"].lower()

        finally:
            if temp_file.exists():
                temp_file.unlink()

    def test_error_invalid_output_format(self):
        """Test error when output format is invalid."""
        file_path = str(FIXTURES_DIR / "sample.py")

        result = self.tool.execute({"file_path": file_path, "output_format": "invalid_format"})

        assert result["success"] is False
        assert result["error"] is not None
        assert "format" in result["error"].lower() or "invalid" in result["error"].lower()

    def test_analyze_file_with_syntax_error(self):
        """Test analyzing file with syntax errors."""
        # Create a file with syntax error
        bad_file = FIXTURES_DIR / "bad_syntax.py"
        try:
            bad_file.write_text("def incomplete_function(\n")

            result = self.tool.execute({"file_path": str(bad_file), "output_format": "toon"})

            # Should still succeed but may include error information
            # (tree-sitter is error-tolerant)
            assert result["success"] is True
            assert result["data"] is not None

        finally:
            if bad_file.exists():
                bad_file.unlink()

    def test_analyze_empty_file(self):
        """Test analyzing empty file."""
        empty_file = FIXTURES_DIR / "empty.py"
        try:
            empty_file.write_text("")

            result = self.tool.execute({"file_path": str(empty_file), "output_format": "toon"})

            assert result["success"] is True
            assert result["data"] is not None

        finally:
            if empty_file.exists():
                empty_file.unlink()

    def test_output_format_case_insensitive(self):
        """Test that output format is case-insensitive."""
        file_path = str(FIXTURES_DIR / "sample.py")

        # Test uppercase
        result = self.tool.execute({"file_path": file_path, "output_format": "TOON"})
        assert result["success"] is True
        assert result["output_format"] == "toon"

        # Test mixed case
        result = self.tool.execute({"file_path": file_path, "output_format": "Markdown"})
        assert result["success"] is True
        assert result["output_format"] == "markdown"

    def test_result_includes_metadata(self):
        """Test that result includes useful metadata."""
        file_path = str(FIXTURES_DIR / "sample.py")

        result = self.tool.execute({"file_path": file_path, "output_format": "toon"})

        # Should include standard result fields
        assert "success" in result
        assert "language" in result
        assert "output_format" in result
        assert "data" in result
        assert "error" in result
