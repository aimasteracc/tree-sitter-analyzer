#!/usr/bin/env python3
"""
Unit tests for format_helper.py

Tests the format helper utility functions for MCP tool output formatting.
After TOON removal, only JSON formatting helpers remain.
"""

from tree_sitter_analyzer.mcp.utils.format_helper import (
    JsonFormatter,
    apply_output_format,
    apply_output_format_to_response,
    format_as_json,
    format_for_file_output,
    format_output,
    get_formatter,
    preformat_diff_snapshot_publish_errors,
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

    def test_format_for_file_output_default_format(self):
        """Test format_for_file_output with default format (JSON)."""
        data = {"key": "value"}
        content, extension = format_for_file_output(data)
        assert isinstance(content, str)
        assert '"key": "value"' in content
        assert extension == ".json"


class TestApplyOutputFormatToResponse:
    """Tests for apply_output_format_to_response function."""

    def test_json_unchanged(self):
        """Test apply_output_format_to_response returns original for JSON format."""
        result = {"key": "value", "number": 42}
        response = apply_output_format_to_response(result, "json")
        assert response == {**result, "format": "json"}
        assert "toon_content" not in response

    def test_success_gets_default_verdict(self):
        """Test successful responses without verdict get INFO."""
        result = {"success": True}
        response = apply_output_format_to_response(result, "json")
        assert response["verdict"] == "INFO"

    def test_explicit_verdict_preserved(self):
        """Test explicit verdict is preserved."""
        result = {"success": True, "verdict": "CAUTION"}
        response = apply_output_format_to_response(result, "json")
        assert response["verdict"] == "CAUTION"

    def test_failure_no_verdict(self):
        """Test failure responses don't get auto-verdict."""
        result = {"success": False, "error": "boom"}
        response = apply_output_format_to_response(result, "json")
        assert "verdict" not in response

    def test_idempotent(self):
        """Test double application stays INFO."""
        first = apply_output_format_to_response({"success": True}, "json")
        second = apply_output_format_to_response(first, "json")
        assert second["verdict"] == "INFO"


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

    def test_get_formatter_and_format(self):
        """Test getting formatter and using it to format data."""
        data = {"key": "value", "number": 42}

        # Get JSON formatter
        json_formatter = get_formatter("json")
        json_result = json_formatter.format(data)
        assert '"key": "value"' in json_result


def test_final_oracle_snapshot_publish_errors() -> None:
    errors, _generic = preformat_diff_snapshot_publish_errors(
        "json", apply_output_format_to_response
    )

    assert errors["DIFF_SNAPSHOT_UNSUPPORTED_FILTER"] == {
        "success": False,
        "format": "json",
        "verdict": "ERROR",
        "error_code": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
        "error": "DIFF_SNAPSHOT_UNSUPPORTED_FILTER",
    }
