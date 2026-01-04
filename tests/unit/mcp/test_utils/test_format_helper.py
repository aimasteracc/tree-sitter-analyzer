#!/usr/bin/env python3
"""
Unit tests for format_helper.py

Tests the format helper utility functions for MCP tool output formatting.
"""

from unittest.mock import MagicMock, patch

from tree_sitter_analyzer.mcp.utils.format_helper import (
    JsonFormatter,
    apply_output_format,
    apply_toon_format_to_response,
    attach_toon_content_to_response,
    format_as_json,
    format_as_toon,
    format_for_file_output,
    format_output,
    get_formatter,
)


class TestFormatOutput:
    """Tests for format_output function."""

    def test_format_output_json(self):
        """Test format_output with JSON format."""
        data = {"key": "value", "number": 42}
        result = format_output(data, "json")
        assert isinstance(result, str)
        assert '"key": "value"' in result
        assert '"number": 42' in result

    def test_format_output_toon(self):
        """Test format_output with TOON format."""
        data = {"key": "value", "number": 42}
        result = format_output(data, "toon")
        assert isinstance(result, str)

    def test_format_output_default_format(self):
        """Test format_output with default format (JSON)."""
        data = {"key": "value"}
        result = format_output(data)
        assert isinstance(result, str)
        assert '"key": "value"' in result

    def test_format_output_empty_dict(self):
        """Test format_output with empty dictionary."""
        data = {}
        result = format_output(data, "json")
        assert result == "{}"

    def test_format_output_nested_dict(self):
        """Test format_output with nested dictionary."""
        data = {"outer": {"inner": {"deep": "value"}}}
        result = format_output(data, "json")
        assert '"outer"' in result
        assert '"inner"' in result
        assert '"deep": "value"' in result


class TestFormatAsJson:
    """Tests for format_as_json function."""

    def test_format_as_json_simple(self):
        """Test format_as_json with simple dictionary."""
        data = {"key": "value"}
        result = format_as_json(data)
        assert result == '{\n  "key": "value"\n}'

    def test_format_as_json_with_numbers(self):
        """Test format_as_json with numbers."""
        data = {"int": 42, "float": 3.14}
        result = format_as_json(data)
        assert '"int": 42' in result
        assert '"float": 3.14' in result

    def test_format_as_json_with_lists(self):
        """Test format_as_json with lists."""
        data = {"items": [1, 2, 3]}
        result = format_as_json(data)
        assert '"items": [' in result
        assert "1," in result
        assert "2," in result
        assert "3" in result

    def test_format_as_json_with_unicode(self):
        """Test format_as_json with Unicode characters."""
        data = {"text": "日本語テスト"}
        result = format_as_json(data)
        assert "日本語テスト" in result

    def test_format_as_json_with_special_chars(self):
        """Test format_as_json with special characters."""
        data = {"text": "Line1\nLine2\tTab"}
        result = format_as_json(data)
        assert "Line1" in result
        assert "Line2" in result


class TestFormatAsToon:
    """Tests for format_as_toon function."""

    @patch("tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter")
    def test_format_as_toon_success(self, mock_formatter_class):
        """Test format_as_toon with successful TOON formatting."""
        mock_formatter = MagicMock()
        mock_formatter.format.return_value = "toon:formatted:content"
        mock_formatter_class.return_value = mock_formatter

        data = {"key": "value"}
        result = format_as_toon(data)

        assert result == "toon:formatted:content"
        mock_formatter_class.assert_called_once()
        mock_formatter.format.assert_called_once_with(data)

    @patch("tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter")
    def test_format_as_toon_import_error_fallback(self, mock_formatter_class):
        """Test format_as_toon falls back to JSON on ImportError."""
        mock_formatter_class.side_effect = ImportError("ToonFormatter not found")

        data = {"key": "value"}
        result = format_as_toon(data)

        assert '"key": "value"' in result

    @patch("tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter")
    def test_format_as_toon_exception_fallback(self, mock_formatter_class):
        """Test format_as_toon falls back to JSON on general exception."""
        mock_formatter = MagicMock()
        mock_formatter.format.side_effect = Exception("Formatting failed")
        mock_formatter_class.return_value = mock_formatter

        data = {"key": "value"}
        result = format_as_toon(data)

        assert '"key": "value"' in result


class TestGetFormatter:
    """Tests for get_formatter function."""

    def test_get_formatter_json(self):
        """Test get_formatter returns JsonFormatter for JSON format."""
        formatter = get_formatter("json")
        assert isinstance(formatter, JsonFormatter)

    def test_get_formatter_default(self):
        """Test get_formatter returns JsonFormatter for default format."""
        formatter = get_formatter()
        assert isinstance(formatter, JsonFormatter)

    @patch("tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter")
    def test_get_formatter_toon(self, mock_formatter_class):
        """Test get_formatter returns ToonFormatter for TOON format."""
        mock_formatter = MagicMock()
        mock_formatter_class.return_value = mock_formatter

        formatter = get_formatter("toon")

        assert formatter == mock_formatter
        mock_formatter_class.assert_called_once()

    @patch("tree_sitter_analyzer.formatters.toon_formatter.ToonFormatter")
    def test_get_formatter_toon_import_error(self, mock_formatter_class):
        """Test get_formatter falls back to JsonFormatter on ImportError."""
        mock_formatter_class.side_effect = ImportError("ToonFormatter not found")

        formatter = get_formatter("toon")

        assert isinstance(formatter, JsonFormatter)


class TestJsonFormatter:
    """Tests for JsonFormatter class."""

    def test_json_formatter_format(self):
        """Test JsonFormatter.format method."""
        formatter = JsonFormatter()
        data = {"key": "value", "number": 42}
        result = formatter.format(data)
        assert isinstance(result, str)
        assert '"key": "value"' in result
        assert '"number": 42' in result

    def test_json_formatter_format_nested(self):
        """Test JsonFormatter.format with nested data."""
        formatter = JsonFormatter()
        data = {"outer": {"inner": "value"}}
        result = formatter.format(data)
        assert '"outer"' in result
        assert '"inner": "value"' in result

    def test_json_formatter_format_list(self):
        """Test JsonFormatter.format with list data."""
        formatter = JsonFormatter()
        data = [1, 2, 3]
        result = formatter.format(data)
        assert result == "[\n  1,\n  2,\n  3\n]"


class TestApplyOutputFormat:
    """Tests for apply_output_format function."""

    def test_apply_output_format_return_dict(self):
        """Test apply_output_format returns dict when return_formatted_string=False."""
        result_dict = {"key": "value", "number": 42}
        result = apply_output_format(result_dict, "json", False)
        assert result == result_dict
        assert isinstance(result, dict)

    def test_apply_output_format_return_string_json(self):
        """Test apply_output_format returns JSON string when requested."""
        result_dict = {"key": "value", "number": 42}
        result = apply_output_format(result_dict, "json", True)
        assert isinstance(result, str)
        assert '"key": "value"' in result

    def test_apply_output_format_return_string_toon(self):
        """Test apply_output_format returns TOON string when requested."""
        result_dict = {"key": "value"}
        result = apply_output_format(result_dict, "toon", True)
        assert isinstance(result, str)

    def test_apply_output_format_default_params(self):
        """Test apply_output_format with default parameters."""
        result_dict = {"key": "value"}
        result = apply_output_format(result_dict)
        assert result == result_dict
        assert isinstance(result, dict)


class TestFormatForFileOutput:
    """Tests for format_for_file_output function."""

    def test_format_for_file_output_json(self):
        """Test format_for_file_output with JSON format."""
        data = {"key": "value", "number": 42}
        content, extension = format_for_file_output(data, "json")
        assert isinstance(content, str)
        assert '"key": "value"' in content
        assert extension == ".json"

    def test_format_for_file_output_toon(self):
        """Test format_for_file_output with TOON format."""
        data = {"key": "value"}
        content, extension = format_for_file_output(data, "toon")
        assert isinstance(content, str)
        assert extension == ".toon"

    def test_format_for_file_output_default_format(self):
        """Test format_for_file_output with default format (JSON)."""
        data = {"key": "value"}
        content, extension = format_for_file_output(data)
        assert isinstance(content, str)
        assert '"key": "value"' in content
        assert extension == ".json"


class TestApplyToonFormatToResponse:
    """Tests for apply_toon_format_to_response function."""

    def test_apply_toon_format_json_unchanged(self):
        """Test apply_toon_format_to_response returns original for JSON format."""
        result = {"key": "value", "number": 42}
        response = apply_toon_format_to_response(result, "json")
        assert response == result
        assert "toon_content" not in response

    def test_apply_toon_format_toon_with_results(self):
        """Test apply_toon_format_to_response removes results field."""
        result = {
            "results": [{"id": 1}, {"id": 2}],
            "metadata": {"total": 2},
        }
        response = apply_toon_format_to_response(result, "toon")
        assert "results" not in response
        assert "metadata" in response
        assert response["metadata"] == {"total": 2}
        assert "format" in response
        assert response["format"] == "toon"
        assert "toon_content" in response

    def test_apply_toon_format_toon_with_matches(self):
        """Test apply_toon_format_to_response removes matches field."""
        result = {
            "matches": [{"line": 1}, {"line": 2}],
            "query": "test",
        }
        response = apply_toon_format_to_response(result, "toon")
        assert "matches" not in response
        assert "query" in response
        assert response["query"] == "test"
        assert "format" in response
        assert "toon_content" in response

    def test_apply_toon_format_toon_with_content(self):
        """Test apply_toon_format_to_response removes content field."""
        result = {
            "content": "file content here",
            "file_path": "/path/to/file.txt",
        }
        response = apply_toon_format_to_response(result, "toon")
        assert "content" not in response
        assert "file_path" in response
        assert response["file_path"] == "/path/to/file.txt"
        assert "format" in response
        assert "toon_content" in response

    def test_apply_toon_format_toon_with_multiple_redundant_fields(self):
        """Test apply_toon_format_to_response removes multiple redundant fields."""
        result = {
            "results": [{"id": 1}],
            "matches": [{"line": 1}],
            "content": "content",
            "data": {"key": "value"},
            "items": [1, 2, 3],
            "files": ["/path1", "/path2"],
            "lines": ["line1", "line2"],
            "table_output": "table",
            "metadata": {"count": 10},
            "status": "success",
        }
        response = apply_toon_format_to_response(result, "toon")
        # All redundant fields should be removed
        assert "results" not in response
        assert "matches" not in response
        assert "content" not in response
        assert "data" not in response
        assert "items" not in response
        assert "files" not in response
        assert "lines" not in response
        assert "table_output" not in response
        # Metadata fields should be preserved
        assert "metadata" in response
        assert response["metadata"] == {"count": 10}
        assert "status" in response
        assert response["status"] == "success"
        # TOON-specific fields should be present
        assert "format" in response
        assert response["format"] == "toon"
        assert "toon_content" in response

    def test_apply_toon_format_toon_preserves_all_metadata(self):
        """Test apply_toon_format_to_response preserves all non-redundant fields."""
        result = {
            "results": [{"id": 1}],
            "query": "test",
            "file_path": "/path/to/file.txt",
            "language": "python",
            "line_count": 100,
            "duration_ms": 50,
            "status": "success",
            "error": None,
        }
        response = apply_toon_format_to_response(result, "toon")
        assert "results" not in response
        assert "query" in response
        assert "file_path" in response
        assert "language" in response
        assert "line_count" in response
        assert "duration_ms" in response
        assert "status" in response
        assert "error" in response
        assert "format" in response
        assert "toon_content" in response

    @patch("tree_sitter_analyzer.mcp.utils.format_helper.format_as_toon")
    def test_apply_toon_format_exception_fallback(self, mock_format_as_toon):
        """Test apply_toon_format_to_response falls back on exception."""
        mock_format_as_toon.side_effect = Exception("Formatting failed")
        result = {"key": "value"}
        response = apply_toon_format_to_response(result, "toon")
        assert response == result


class TestAttachToonContentToResponse:
    """Tests for attach_toon_content_to_response function."""

    def test_attach_toon_content_success(self):
        """Test attach_toon_content_to_response adds TOON content."""
        result = {"key": "value", "number": 42}
        response = attach_toon_content_to_response(result)
        assert "key" in response
        assert response["key"] == "value"
        assert "number" in response
        assert response["number"] == 42
        assert "format" in response
        assert response["format"] == "toon"
        assert "toon_content" in response
        assert isinstance(response["toon_content"], str)

    def test_attach_toon_content_preserves_original(self):
        """Test attach_toon_content_to_response preserves all original fields."""
        result = {
            "results": [{"id": 1}, {"id": 2}],
            "matches": [{"line": 1}],
            "content": "file content",
            "metadata": {"total": 2},
            "status": "success",
        }
        response = attach_toon_content_to_response(result)
        # All original fields should be preserved
        assert "results" in response
        assert response["results"] == [{"id": 1}, {"id": 2}]
        assert "matches" in response
        assert response["matches"] == [{"line": 1}]
        assert "content" in response
        assert response["content"] == "file content"
        assert "metadata" in response
        assert response["metadata"] == {"total": 2}
        assert "status" in response
        assert response["status"] == "success"
        # TOON fields should be added
        assert "format" in response
        assert response["format"] == "toon"
        assert "toon_content" in response

    def test_attach_toon_content_does_not_modify_original(self):
        """Test attach_toon_content_to_response does not modify original dict."""
        result = {"key": "value"}
        original_result = result.copy()
        response = attach_toon_content_to_response(result)
        assert "format" not in result
        assert "toon_content" not in result
        assert result == original_result
        assert "format" in response
        assert "toon_content" in response

    @patch("tree_sitter_analyzer.mcp.utils.format_helper.format_as_toon")
    def test_attach_toon_content_exception_fallback(self, mock_format_as_toon):
        """Test attach_toon_content_to_response falls back on exception."""
        mock_format_as_toon.side_effect = Exception("Formatting failed")
        result = {"key": "value"}
        response = attach_toon_content_to_response(result)
        assert response == result
        assert "format" not in response
        assert "toon_content" not in response


class TestIntegration:
    """Integration tests for format_helper module."""

    def test_format_workflow_json(self):
        """Test complete formatting workflow for JSON."""
        data = {"results": [{"id": 1}], "metadata": {"total": 1}}

        # Step 1: Format as JSON string
        json_string = format_output(data, "json")
        assert isinstance(json_string, str)
        assert '"results"' in json_string

        # Step 2: Apply output format (return dict for MCP)
        mcp_result = apply_output_format(data, "json", False)
        assert mcp_result == data

        # Step 3: Format for file output
        content, ext = format_for_file_output(data, "json")
        assert ext == ".json"
        assert '"results"' in content

    def test_format_workflow_toon(self):
        """Test complete formatting workflow for TOON."""
        data = {"results": [{"id": 1}], "metadata": {"total": 1}}

        # Step 1: Format as TOON string
        toon_string = format_output(data, "toon")
        assert isinstance(toon_string, str)

        # Step 2: Apply TOON format to response
        toon_response = apply_toon_format_to_response(data, "toon")
        assert "results" not in toon_response
        assert "metadata" in toon_response
        assert "toon_content" in toon_response

        # Step 3: Format for file output
        content, ext = format_for_file_output(data, "toon")
        assert ext == ".toon"
        assert isinstance(content, str)

    def test_get_formatter_and_format(self):
        """Test getting formatter and using it to format data."""
        data = {"key": "value", "number": 42}

        # Get JSON formatter
        json_formatter = get_formatter("json")
        json_result = json_formatter.format(data)
        assert '"key": "value"' in json_result

        # Get TOON formatter (will use JsonFormatter as fallback in test)
        toon_formatter = get_formatter("toon")
        toon_result = toon_formatter.format(data)
        assert isinstance(toon_result, str)

    def test_attach_vs_apply_toon_difference(self):
        """Test difference between attach and apply TOON functions."""
        data = {
            "results": [{"id": 1}],
            "metadata": {"total": 1},
            "status": "success",
        }

        # apply_toon_format_to_response removes redundant fields
        applied = apply_toon_format_to_response(data, "toon")
        assert "results" not in applied
        assert "metadata" in applied
        assert "status" in applied

        # attach_toon_content_to_response preserves all fields
        attached = attach_toon_content_to_response(data)
        assert "results" in attached
        assert attached["results"] == [{"id": 1}]
        assert "metadata" in attached
        assert "status" in attached
        assert "toon_content" in attached
