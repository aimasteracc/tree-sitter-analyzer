"""
Integration tests for ExtractCodeSectionTool MCP tool.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

TDD Phases:
- Phase 1: Basic extraction tests (5 tests)
- Phase 2: Output format tests (2 tests)
- Phase 3: Encoding tests (3 tests)
- Phase 4: Error handling tests (3 tests)
"""

from pathlib import Path

import pytest


class TestExtractCodeSectionTool:
    """Tests for ExtractCodeSectionTool MCP tool."""

    def test_tool_initialization(self):
        """Test tool initialization and basic properties."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        assert tool.get_name() == "extract_code_section"
        assert "Extract specific code sections" in tool.get_description()

    def test_tool_schema(self):
        """Test tool schema definition."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        schema = tool.get_schema()

        # Required fields exist in properties
        assert "file_path" in schema["properties"]
        assert "start_line" in schema["properties"]
        assert "end_line" in schema["properties"]
        assert "output_format" in schema["properties"]

        # Type validation
        assert schema["properties"]["file_path"]["type"] == "string"
        assert schema["properties"]["start_line"]["type"] == "integer"
        assert schema["properties"]["end_line"]["type"] == "integer"
        assert schema["properties"]["output_format"]["type"] == "string"

        # Default and enum
        assert schema["properties"]["output_format"]["default"] == "toon"
        assert set(schema["properties"]["output_format"]["enum"]) == {"toon", "markdown"}

        # Batch mode support
        assert "requests" in schema["properties"]

    # Phase 1: Basic Extraction Tests
    def test_extract_basic_range(self):
        """Test extracting a basic range of lines."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        # Use existing sample.py fixture
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"
        assert fixture_path.exists(), f"Fixture not found: {fixture_path}"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 10,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["file_path"] == str(fixture_path)
        assert result["range"]["start_line"] == 1
        assert result["range"]["end_line"] == 10
        assert result["lines_extracted"] == 10
        assert len(result["content"]) > 0
        assert "import" in result["content"]  # Should contain import statements

    def test_extract_to_end_of_file(self):
        """Test extracting from start_line to end of file (end_line omitted)."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {"file_path": str(fixture_path), "start_line": 50, "output_format": "toon"}
        )

        assert result["success"] is True
        assert result["range"]["start_line"] == 50
        # end_line should be total file lines
        assert result["range"]["end_line"] > 50
        assert result["lines_extracted"] > 0

    def test_extract_single_line(self):
        """Test extracting a single line (start_line == end_line)."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 5,
                "end_line": 5,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["range"]["start_line"] == 5
        assert result["range"]["end_line"] == 5
        assert result["lines_extracted"] == 1
        # Single line content
        assert "\n" not in result["content"].strip()

    def test_extract_first_line(self):
        """Test extracting the first line of file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 1,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["lines_extracted"] == 1

    def test_extract_last_line(self):
        """Test extracting the last line of file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        # First get total line count
        with open(fixture_path, encoding="utf-8") as f:
            total_lines = len(f.readlines())

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": total_lines,
                "end_line": total_lines,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["lines_extracted"] == 1

    # Phase 2: Output Format Tests
    def test_extract_toon_format(self):
        """Test TOON output format."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 5,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        # TOON format returns structured dict
        assert "file_path" in result
        assert "range" in result
        assert "lines_extracted" in result
        assert "content_length" in result
        assert "content" in result

    def test_extract_markdown_format(self):
        """Test Markdown output format."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 5,
                "output_format": "markdown",
            }
        )

        assert result["success"] is True
        # Markdown format returns formatted string in 'data' field
        assert "data" in result
        assert "# Code Section Extract" in result["data"]
        assert "**File**:" in result["data"]
        assert "**Range**:" in result["data"]
        assert "```python" in result["data"]

    # Phase 3: Encoding Tests (Future - skip for now if no encoding detector yet)
    @pytest.mark.skip(reason="Encoding detector not implemented yet")
    def test_extract_japanese_shift_jis(self):
        """Test extracting Japanese Shift-JIS encoded file."""
        pass

    @pytest.mark.skip(reason="Encoding detector not implemented yet")
    def test_extract_chinese_gbk(self):
        """Test extracting Chinese GBK encoded file."""
        pass

    @pytest.mark.skip(reason="Encoding detector not implemented yet")
    def test_extract_utf8_with_bom(self):
        """Test extracting UTF-8 with BOM file."""
        pass

    # Phase 4: Error Handling Tests
    def test_extract_file_not_found(self):
        """Test error handling for non-existent file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "file_path": "/nonexistent/file.py",
                "start_line": 1,
                "end_line": 10,
                "output_format": "toon",
            }
        )

        assert result["success"] is False
        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_extract_invalid_range(self):
        """Test error handling for invalid range (end_line < start_line)."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 10,
                "end_line": 5,
                "output_format": "toon",
            }
        )

        assert result["success"] is False
        assert "error" in result
        assert "end_line must be >= start_line" in result["error"]

    def test_extract_start_line_exceeds_file(self):
        """Test error handling for start_line exceeding file length."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 99999,
                "end_line": 100000,
                "output_format": "toon",
            }
        )

        assert result["success"] is False
        assert "error" in result
        assert "exceeds file length" in result["error"]

    # Phase 5: Token Protection Tests
    def test_suppress_content(self):
        """Test suppress_content parameter to save tokens."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 10,
                "suppress_content": True,
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert "content_suppressed" in result
        assert result["content_suppressed"] is True
        assert "content" not in result  # Content should be suppressed

    def test_max_content_length(self):
        """Test max_content_length truncation."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 1,
                "end_line": 50,
                "max_content_length": 100,  # Very small limit
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert "truncated" in result
        assert result["truncated"] is True
        assert len(result["content"]) == 100 + len("\n... [truncated]")

    # Phase 6: Batch Mode Tests
    def test_batch_mode_basic(self):
        """Test batch mode with multiple files."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(fixture_path),
                        "sections": [
                            {"start_line": 1, "end_line": 5, "label": "imports"},
                            {"start_line": 10, "end_line": 15, "label": "class_def"},
                        ],
                    }
                ],
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["count_files"] == 1
        assert result["count_sections"] == 2
        assert len(result["results"]) == 1
        assert len(result["results"][0]["sections"]) == 2

    def test_batch_mode_multiple_files(self):
        """Test batch mode with multiple files."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_dir = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures"
        sample_py = str(fixture_dir / "sample.py")
        sample_ts = str(fixture_dir / "sample.ts")

        result = tool.execute(
            {
                "requests": [
                    {"file_path": sample_py, "sections": [{"start_line": 1, "end_line": 5}]},
                    {"file_path": sample_ts, "sections": [{"start_line": 1, "end_line": 3}]},
                ],
                "output_format": "toon",
            }
        )

        assert result["success"] is True
        assert result["count_files"] == 2
        assert result["count_sections"] == 2

    def test_batch_mode_file_not_found(self):
        """Test batch mode error handling for missing file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": "/nonexistent/file.py",
                        "sections": [{"start_line": 1, "end_line": 5}],
                    }
                ],
                "output_format": "toon",
                "fail_fast": False,  # Partial success mode
            }
        )

        assert result["success"] is False  # No sections succeeded
        assert result["count_files"] == 1
        assert result["count_sections"] == 0
        assert len(result["results"]) == 1
        assert len(result["results"][0]["errors"]) > 0

    def test_batch_mode_fail_fast(self):
        """Test batch mode fail_fast parameter."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": "/nonexistent/file.py",
                        "sections": [{"start_line": 1, "end_line": 5}],
                    }
                ],
                "output_format": "toon",
                "fail_fast": True,  # Stop on first error
            }
        )

        assert result["success"] is False
        assert "error" in result  # Should return error immediately

    def test_batch_mode_mutually_exclusive(self):
        """Test that batch mode is mutually exclusive with single mode."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),  # Single mode param
                "requests": [{"file_path": str(fixture_path), "sections": []}],  # Batch mode param
                "start_line": 1,
            }
        )

        assert result["success"] is False
        assert "mutually exclusive" in result["error"]

    def test_batch_mode_invalid_request_entry(self):
        """Test batch mode with invalid request entry."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": ["not_a_dict"],  # Invalid entry (not a dict)
                "fail_fast": False,
            }
        )

        assert result["success"] is False
        assert result["errors_summary"]["errors"] > 0

    def test_batch_mode_missing_file_path(self):
        """Test batch mode with missing file_path."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": [
                    {"sections": [{"start_line": 1}]}  # Missing file_path
                ],
                "fail_fast": False,
            }
        )

        assert result["success"] is False
        assert result["errors_summary"]["errors"] > 0

    def test_batch_mode_invalid_section(self):
        """Test batch mode with invalid section structure."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(fixture_path),
                        "sections": ["not_a_dict"],  # Invalid section
                    }
                ],
                "fail_fast": False,
            }
        )

        assert result["success"] is False
        assert result["errors_summary"]["errors"] > 0

    def test_batch_mode_invalid_start_line(self):
        """Test batch mode with invalid start_line."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(fixture_path),
                        "sections": [
                            {"start_line": 0},  # Invalid (< 1)
                            {"start_line": 10, "end_line": 5},  # Invalid (end < start)
                        ],
                    }
                ],
                "fail_fast": False,
            }
        )

        assert result["success"] is False
        assert result["errors_summary"]["errors"] >= 2

    def test_batch_mode_empty_content(self):
        """Test batch mode with section that returns empty content."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        # Get total lines
        with open(fixture_path, encoding="utf-8") as f:
            total_lines = len(f.readlines())

        result = tool.execute(
            {
                "requests": [
                    {
                        "file_path": str(fixture_path),
                        "sections": [
                            {
                                "start_line": total_lines + 1,
                                "end_line": total_lines + 2,
                            }  # Beyond EOF
                        ],
                    }
                ],
                "fail_fast": False,
            }
        )

        # Should handle gracefully with error
        assert "errors" in result["results"][0] or result["count_sections"] == 0

    def test_single_mode_file_not_file(self):
        """Test error handling when path is directory not file."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_dir = Path(__file__).parent.parent / "fixtures"

        result = tool.execute(
            {
                "file_path": str(fixture_dir),  # Directory, not file
                "start_line": 1,
                "end_line": 5,
            }
        )

        assert result["success"] is False
        assert "Not a file" in result["error"]

    def test_single_mode_missing_start_line(self):
        """Test error handling when start_line is missing."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path)
                # Missing start_line
            }
        )

        assert result["success"] is False
        assert "start_line is required" in result["error"]

    def test_single_mode_invalid_start_line_negative(self):
        """Test error handling for start_line < 1."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        result = tool.execute(
            {
                "file_path": str(fixture_path),
                "start_line": 0,  # Invalid
            }
        )

        assert result["success"] is False
        assert "start_line must be >= 1" in result["error"]

    def test_batch_mode_too_many_sections_per_file(self):
        """Test batch mode with too many sections per file (exceeds limit)."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        # Create 51 sections (exceeds max_sections_per_file=50)
        sections = [{"start_line": i, "end_line": i} for i in range(1, 52)]

        result = tool.execute(
            {
                "requests": [{"file_path": str(fixture_path), "sections": sections}],
                "allow_truncate": False,  # Don't allow truncation
                "fail_fast": True,
            }
        )

        assert result["success"] is False
        assert "Too many sections" in result["error"]

    def test_batch_mode_allow_truncate_sections(self):
        """Test batch mode with allow_truncate for too many sections."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()
        fixture_path = Path(__file__).parent.parent / "fixtures" / "analyze_fixtures" / "sample.py"

        # Create 51 sections (exceeds max_sections_per_file=50)
        sections = [{"start_line": i, "end_line": i} for i in range(1, 52)]

        result = tool.execute(
            {
                "requests": [{"file_path": str(fixture_path), "sections": sections}],
                "allow_truncate": True,  # Allow truncation
                "fail_fast": False,
            }
        )

        # Should succeed with truncation
        assert result["truncated"] is True
        # Should have at most 50 sections
        assert len(result["results"][0]["sections"]) <= 50

    def test_single_mode_missing_file_path(self):
        """Test error when file_path is missing in single mode."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "start_line": 1,
                "end_line": 10,
                # Missing file_path
            }
        )

        assert result["success"] is False
        assert "file_path is required" in result["error"]

    def test_batch_mode_invalid_requests_type(self):
        """Test batch mode with non-list requests parameter."""
        from tree_sitter_analyzer_v2.mcp.tools.extract import ExtractCodeSectionTool

        tool = ExtractCodeSectionTool()

        result = tool.execute(
            {
                "requests": "not_a_list"  # Should be a list
            }
        )

        assert result["success"] is False
        assert "must be a list" in result["error"]
