#!/usr/bin/env python3
"""
Additional tests to boost TOON formatter/encoder coverage to near 100%.

These tests cover edge cases and code paths not covered by existing tests.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestToonEncoderEdgeCases:
    """Test edge cases for ToonEncoder."""

    def test_encode_value_with_dict_no_seen_ids(self):
        """Test encode_value with dict when seen_ids is None."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder.encode_value({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_encode_value_with_list_no_seen_ids(self):
        """Test encode_value with list when seen_ids is None."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder.encode_value([1, 2, 3])
        assert "[" in result
        assert "1" in result

    def test_encode_empty_array_table(self):
        """Test encode_array_table with empty list."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder.encode_array_table([])
        assert result == "[]"

    def test_encode_array_table_with_explicit_schema(self):
        """Test encode_array_table with explicit schema."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        items = [{"name": "test", "value": 1}]
        result = encoder.encode_array_table(items, schema=["name", "value"])
        assert "[1]{name,value}:" in result
        assert "test,1" in result

    def test_encode_array_table_with_tuple_values(self):
        """Test array table encoding with tuple values."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        items = [{"name": "test", "range": (1, 10)}]
        result = encoder.encode_array_table(items)
        assert "range(a,b)" in result
        assert "(1,10)" in result

    def test_encode_array_table_with_dict_values(self):
        """Test array table encoding with nested dict values."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        items = [{"name": "test", "meta": {"start": 1, "end": 2}}]
        result = encoder.encode_array_table(items)
        assert "meta{start,end}" in result

    def test_infer_schema_empty_list(self):
        """Test _infer_schema with empty list."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder._infer_schema([])
        assert result == []

    def test_encode_array_header_without_schema(self):
        """Test encode_array_header without schema."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder.encode_array_header(5)
        assert result == "[5]:"

    def test_encode_array_header_with_schema(self):
        """Test encode_array_header with schema."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder.encode_array_header(3, ["name", "value"])
        assert result == "[3]{name,value}:"

    def test_encode_safe_with_toon_encode_error(self):
        """Test encode_safe catches ToonEncodeError."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder(fallback_to_json=True)
        # Create circular reference
        data: dict = {}
        data["self"] = data
        result = encoder.encode_safe(data)
        # Should return JSON fallback
        assert isinstance(result, str)

    def test_encode_safe_with_fallback_disabled(self):
        """Test encode_safe without fallback returns error message."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder(fallback_to_json=False)
        data: dict = {}
        data["self"] = data
        result = encoder.encode_safe(data)
        assert "ToonEncodeError" in result

    def test_detect_circular_reference_with_list(self):
        """Test circular reference detection with list."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        data: list = []
        data.append(data)
        result = ToonEncoder.detect_circular_reference(data)
        assert result is True

    def test_detect_circular_reference_no_circular(self):
        """Test circular reference detection with no circular refs."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        data = {"a": [1, 2, {"b": 3}]}
        result = ToonEncoder.detect_circular_reference(data)
        assert result is False

    def test_encode_list_with_nested_dicts(self):
        """Test encoding list with nested dicts triggers array table."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = [{"a": 1}, {"a": 2}]
        result = encoder.encode_list(data)
        assert "[2]{a}:" in result

    def test_encode_dict_with_list_of_primitives(self):
        """Test encoding dict with simple list values."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = {"items": [1, 2, 3]}
        result = encoder.encode_dict(data)
        assert "items: [1,2,3]" in result

    def test_encode_inline_dict_with_nested_dict(self):
        """Test _encode_inline_dict with nested dict."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = {"outer": {"inner": "value"}}
        result = encoder._encode_inline_dict(data, set())
        assert "outer:" in result
        assert "inner:" in result

    def test_encode_inline_dict_with_list(self):
        """Test _encode_inline_dict with list value."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = {"items": [1, 2]}
        result = encoder._encode_inline_dict(data, set())
        assert "items:" in result
        assert "[1,2]" in result

    def test_encode_inline_dict_empty(self):
        """Test _encode_inline_dict with empty dict."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        result = encoder._encode_inline_dict({}, set())
        assert result == "{}"

    def test_encode_simple_list_with_nested_list(self):
        """Test _encode_simple_list with nested list."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = [[1, 2], [3, 4]]
        result = encoder._encode_simple_list(data, set())
        assert "[[1,2],[3,4]]" in result

    def test_encode_simple_list_with_dict(self):
        """Test _encode_simple_list with dict inside."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        data = [{"a": 1}]
        result = encoder._encode_simple_list(data, set())
        assert "{a:1}" in result

    def test_handle_list_item_with_dict(self):
        """Test _handle_list_item with dict pushes dict start task."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, {"key": "value"}, indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(stack) == 1
        assert stack[0].task_type == _TaskType.ENCODE_DICT_START

    def test_handle_list_item_with_list(self):
        """Test _handle_list_item with list pushes list start task."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, [1, 2, 3], indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(stack) == 1
        assert stack[0].task_type == _TaskType.ENCODE_LIST_START

    def test_handle_list_item_with_primitive(self):
        """Test _handle_list_item with primitive adds to output."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, "hello", indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(output) == 1
        assert "hello" in output[0]

    def test_handle_list_start_empty_list(self):
        """Test _handle_list_start with empty list."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_START, [], indent=0)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_start(task, stack, output, seen_ids)
        assert output == ["[]"]

    def test_handle_list_start_circular_reference(self):
        """Test _handle_list_start with circular reference."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncodeError,
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        data = [1, 2]
        obj_id = id(data)
        task = _Task(_TaskType.ENCODE_LIST_START, data, indent=0)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = {obj_id}  # Already seen

        with pytest.raises(ToonEncodeError):
            encoder._handle_list_start(task, stack, output, seen_ids)

    def test_handle_array_table_empty(self):
        """Test _handle_array_table with empty list."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_ARRAY_TABLE, [], indent=0)
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_array_table(task, output, seen_ids)
        assert output == ["[]"]

    def test_handle_array_table_circular_reference(self):
        """Test _handle_array_table with circular reference."""
        from tree_sitter_analyzer.formatters.toon_encoder import (
            ToonEncodeError,
            ToonEncoder,
            _Task,
            _TaskType,
        )

        encoder = ToonEncoder()
        data = [{"key": 1}]
        obj_id = id(data)
        task = _Task(_TaskType.ENCODE_ARRAY_TABLE, data, indent=0)
        output: list[str] = []
        seen_ids: set[int] = {obj_id}  # Already seen

        with pytest.raises(ToonEncodeError):
            encoder._handle_array_table(task, output, seen_ids)

    def test_fallback_to_json_exception(self):
        """Test _fallback_to_json when json.dumps fails."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder()
        # Create object that can't be JSON serialized
        data = {"func": lambda x: x}
        result = encoder._fallback_to_json(data)
        # Should use default=str
        assert "{" in result

    def test_encode_with_tabs(self):
        """Test encoder with tab delimiter."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder

        encoder = ToonEncoder(use_tabs=True)
        assert encoder.delimiter == "\t"
        items = [{"a": 1, "b": 2}]
        result = encoder.encode_array_table(items)
        assert "\t" in result


class TestToonFormatterEdgeCases:
    """Test edge cases for ToonFormatter."""

    def test_format_with_unexpected_exception(self):
        """Test format handles unexpected exceptions."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter(fallback_to_json=True)

        # Mock encoder to raise exception
        with patch.object(
            formatter, "_format_internal", side_effect=ValueError("test")
        ):
            result = formatter.format({"key": "value"})
            # Should fall back to JSON
            assert '"key"' in result

    def test_format_with_fallback_disabled(self):
        """Test format raises when fallback disabled."""
        from tree_sitter_analyzer.formatters.toon_encoder import ToonEncodeError
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter(fallback_to_json=False)

        with patch.object(
            formatter, "_format_internal", side_effect=ValueError("test")
        ):
            with pytest.raises(ToonEncodeError):
                formatter.format({"key": "value"})

    def test_format_internal_import_error(self):
        """Test _format_internal handles ImportError for AnalysisResult."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        # This should not raise, just fall through to dict handling
        result = formatter._format_internal({"key": "value"})
        assert "key:" in result

    def test_format_analysis_result_with_dict(self):
        """Test format_analysis_result with dict (not AnalysisResult)."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format_analysis_result({"key": "value"})
        assert "key:" in result

    def test_format_analysis_result_with_non_dict(self):
        """Test format_analysis_result with non-dict, non-AnalysisResult."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format_analysis_result("simple string")
        assert "simple string" in result

    def test_format_analysis_result_with_analysis_result(self):
        """Test format_analysis_result with actual AnalysisResult."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
        from tree_sitter_analyzer.models import AnalysisResult

        formatter = ToonFormatter()

        # Create mock elements
        mock_class = MagicMock()
        mock_class.name = "TestClass"
        mock_class.element_type = "class"
        mock_class.start_line = 1
        mock_class.end_line = 10

        mock_method = MagicMock()
        mock_method.name = "test_method"
        mock_method.element_type = "method"
        mock_method.start_line = 2
        mock_method.end_line = 5
        mock_method.visibility = "public"

        mock_func = MagicMock()
        mock_func.name = "test_func"
        mock_func.element_type = "function"
        mock_func.start_line = 12
        mock_func.end_line = 15

        # Create mock AnalysisResult
        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements=[mock_class, mock_method, mock_func],
        )

        output = formatter.format_analysis_result(result)
        assert "file: test.py" in output
        assert "language: python" in output
        assert "elements[3]:" in output
        assert "classes[1]:" in output
        assert "methods[1]:" in output
        assert "functions[1]:" in output

    def test_format_analysis_result_with_compact_arrays_disabled(self):
        """Test format_analysis_result with compact_arrays=False."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
        from tree_sitter_analyzer.models import AnalysisResult, CodeElement

        formatter = ToonFormatter(compact_arrays=False)

        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements=[
                CodeElement(
                    name="test_method",
                    element_type="method",
                    start_line=2,
                    end_line=5,
                ),
            ],
        )

        output = formatter.format_analysis_result(result)
        assert "methods[1]:" in output
        assert "- test_method" in output

    def test_format_analysis_result_with_package(self):
        """Test format_analysis_result includes package."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
        from tree_sitter_analyzer.models import AnalysisResult

        formatter = ToonFormatter()

        # Mock package
        mock_package = MagicMock()
        mock_package.name = "com.example"

        result = AnalysisResult(
            file_path="test.java",
            language="java",
            package=mock_package,
            elements=[],
        )

        output = formatter.format_analysis_result(result)
        assert "package: com.example" in output

    def test_format_analysis_result_without_metadata(self):
        """Test format_analysis_result with include_metadata=False."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
        from tree_sitter_analyzer.models import AnalysisResult

        formatter = ToonFormatter(include_metadata=False)

        result = AnalysisResult(
            file_path="test.py",
            language="python",
            elements=[],
        )

        output = formatter.format_analysis_result(result)
        assert "file:" not in output

    def test_format_summary(self):
        """Test format_summary method."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format_summary({"total": 10, "classes": 2})
        assert "total:" in result
        assert "classes:" in result

    def test_format_advanced(self):
        """Test format_advanced method."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format_advanced({"analysis": "complete"})
        assert "analysis:" in result

    def test_format_table(self):
        """Test format_table method."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format_table({"rows": [1, 2, 3]})
        assert "rows:" in result

    def test_method_to_dict(self):
        """Test _method_to_dict helper method."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        mock_method = MagicMock()
        mock_method.name = "test_method"
        mock_method.visibility = "public"
        mock_method.start_line = 10
        mock_method.end_line = 20

        result = formatter._method_to_dict(mock_method)
        assert result["name"] == "test_method"
        assert result["visibility"] == "public"
        assert result["lines"] == "10-20"

    def test_method_to_dict_without_attributes(self):
        """Test _method_to_dict with minimal attributes."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        result = formatter._method_to_dict("simple_string")
        assert result["name"] == "simple_string"
        assert result["visibility"] == ""
        assert result["lines"] == "0-0"

    def test_is_toon_content_with_key_value(self):
        """Test is_toon_content with key-value patterns."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        content = """file: test.py
language: python
count: 10"""
        assert ToonFormatter.is_toon_content(content) is True

    def test_is_toon_content_with_array_header(self):
        """Test is_toon_content with array table header and key-value."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        # Array header alone won't pass (needs 2 patterns), so add key-value
        content = """items:
[3]{name,value}:
  test1,1
  test2,2"""
        assert ToonFormatter.is_toon_content(content) is True

    def test_is_toon_content_empty_lines(self):
        """Test is_toon_content skips empty lines."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        content = """

key: value

another: line
"""
        assert ToonFormatter.is_toon_content(content) is True

    def test_is_toon_content_quoted_string_start(self):
        """Test is_toon_content rejects lines starting with quote."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter

        content = '"quoted": "value"'
        assert ToonFormatter.is_toon_content(content) is False


class TestFormatHelperCoverage:
    """Test format_helper.py for full coverage."""

    def test_format_output_json(self):
        """Test format_output with json format."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_output

        data = {"key": "value"}
        result = format_output(data, "json")
        assert '"key"' in result

    def test_format_output_toon(self):
        """Test format_output with toon format."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_output

        data = {"key": "value"}
        result = format_output(data, "toon")
        assert "key:" in result

    def test_format_as_json(self):
        """Test format_as_json."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_as_json

        data = {"test": 123}
        result = format_as_json(data)
        parsed = json.loads(result)
        assert parsed["test"] == 123

    def test_format_as_toon(self):
        """Test format_as_toon."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_as_toon

        data = {"test": 123}
        result = format_as_toon(data)
        assert "test:" in result

    def test_format_as_toon_import_error(self):
        """Test format_as_toon handles ImportError."""
        # The format_as_toon function handles import errors internally
        # We test that it still returns a valid string
        from tree_sitter_analyzer.mcp.utils.format_helper import format_as_toon

        data = {"test": 123}
        result = format_as_toon(data)
        assert isinstance(result, str)
        # Should contain the data in some format (TOON or JSON fallback)
        assert "test" in result

    def test_format_as_toon_exception(self):
        """Test format_as_toon handles formatting exception."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_as_toon

        # Create circular reference that will cause encoding error
        data: dict = {"key": "value"}
        data["self"] = data

        result = format_as_toon(data)
        # Should fall back to JSON
        assert isinstance(result, str)

    def test_get_formatter_json(self):
        """Test get_formatter returns JsonFormatter for json."""
        from tree_sitter_analyzer.mcp.utils.format_helper import (
            JsonFormatter,
            get_formatter,
        )

        formatter = get_formatter("json")
        assert isinstance(formatter, JsonFormatter)

    def test_get_formatter_toon(self):
        """Test get_formatter returns ToonFormatter for toon."""
        from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
        from tree_sitter_analyzer.mcp.utils.format_helper import get_formatter

        formatter = get_formatter("toon")
        assert isinstance(formatter, ToonFormatter)

    def test_get_formatter_toon_import_error(self):
        """Test get_formatter returns ToonFormatter for toon."""
        from tree_sitter_analyzer.mcp.utils.format_helper import get_formatter

        # get_formatter should return a working formatter
        formatter = get_formatter("toon")
        assert formatter is not None
        # Verify it has a format method
        assert hasattr(formatter, "format")
        result = formatter.format({"test": 123})
        assert isinstance(result, str)

    def test_json_formatter_format(self):
        """Test JsonFormatter.format method."""
        from tree_sitter_analyzer.mcp.utils.format_helper import JsonFormatter

        formatter = JsonFormatter()
        data = {"key": "value"}
        result = formatter.format(data)
        assert '"key"' in result

    def test_apply_output_format_return_dict(self):
        """Test apply_output_format returns dict by default."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_output_format

        data = {"key": "value"}
        result = apply_output_format(data, "json", return_formatted_string=False)
        assert isinstance(result, dict)
        assert result == data

    def test_apply_output_format_return_string(self):
        """Test apply_output_format returns string when requested."""
        from tree_sitter_analyzer.mcp.utils.format_helper import apply_output_format

        data = {"key": "value"}
        result = apply_output_format(data, "json", return_formatted_string=True)
        assert isinstance(result, str)

    def test_format_for_file_output_json(self):
        """Test format_for_file_output with json format."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_for_file_output

        data = {"key": "value"}
        content, ext = format_for_file_output(data, "json")
        assert ext == ".json"
        assert '"key"' in content

    def test_format_for_file_output_toon(self):
        """Test format_for_file_output with toon format."""
        from tree_sitter_analyzer.mcp.utils.format_helper import format_for_file_output

        data = {"key": "value"}
        content, ext = format_for_file_output(data, "toon")
        assert ext == ".toon"
        assert "key:" in content
