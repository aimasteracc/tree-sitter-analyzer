#!/usr/bin/env python3
"""
Unit tests for ToonEncoder.

Tests the TOON (Token-Oriented Object Notation) encoder functionality.
"""

import pytest

from tree_sitter_analyzer.formatters.toon_encoder import (
    ToonEncodeError,
    ToonEncoder,
)


class TestToonEncodeError:
    """Tests for ToonEncodeError exception class."""

    def test_init_basic(self):
        """Test basic initialization of ToonEncodeError."""
        error = ToonEncodeError("Test error message")
        assert error.message == "Test error message"
        assert error.data is None
        assert error.cause is None

    def test_init_with_data(self):
        """Test initialization with data."""
        error = ToonEncodeError("Test error", data={"key": "value"})
        assert error.message == "Test error"
        assert error.data == {"key": "value"}

    def test_init_with_cause(self):
        """Test initialization with cause exception."""
        original_error = ValueError("Original error")
        error = ToonEncodeError("Test error", cause=original_error)
        assert error.message == "Test error"
        assert error.cause is original_error

    def test_str_basic(self):
        """Test string representation without cause."""
        error = ToonEncodeError("Test error")
        assert str(error) == "ToonEncodeError: Test error"

    def test_str_with_cause(self):
        """Test string representation with cause."""
        original_error = ValueError("Original error")
        error = ToonEncodeError("Test error", cause=original_error)
        error_str = str(error)
        assert "ToonEncodeError: Test error" in error_str
        assert "caused by: ValueError: Original error" in error_str


class TestToonEncoderInit:
    """Tests for ToonEncoder initialization."""

    def test_init_default(self):
        """Test default initialization."""
        encoder = ToonEncoder()
        assert encoder.use_tabs is False
        assert encoder.delimiter == ","
        assert encoder.fallback_to_json is True
        assert encoder.max_depth == 100
        assert encoder.normalize_paths is True

    def test_init_with_tabs(self):
        """Test initialization with tab delimiter."""
        encoder = ToonEncoder(use_tabs=True)
        assert encoder.use_tabs is True
        assert encoder.delimiter == "\t"

    def test_init_without_fallback(self):
        """Test initialization without JSON fallback."""
        encoder = ToonEncoder(fallback_to_json=False)
        assert encoder.fallback_to_json is False

    def test_init_custom_max_depth(self):
        """Test initialization with custom max depth."""
        encoder = ToonEncoder(max_depth=50)
        assert encoder.max_depth == 50

    def test_init_without_path_normalization(self):
        """Test initialization without path normalization."""
        encoder = ToonEncoder(normalize_paths=False)
        assert encoder.normalize_paths is False


class TestToonEncoderEncodePrimitive:
    """Tests for encoding primitive values."""

    def test_encode_none(self):
        """Test encoding None value."""
        encoder = ToonEncoder()
        result = encoder.encode(None)
        assert result == "null"

    def test_encode_bool_true(self):
        """Test encoding True boolean."""
        encoder = ToonEncoder()
        result = encoder.encode(True)
        assert result == "true"

    def test_encode_bool_false(self):
        """Test encoding False boolean."""
        encoder = ToonEncoder()
        result = encoder.encode(False)
        assert result == "false"

    def test_encode_int(self):
        """Test encoding integer."""
        encoder = ToonEncoder()
        result = encoder.encode(42)
        assert result == "42"

    def test_encode_float(self):
        """Test encoding float."""
        encoder = ToonEncoder()
        result = encoder.encode(3.14)
        assert result == "3.14"

    def test_encode_string_simple(self):
        """Test encoding simple string."""
        encoder = ToonEncoder()
        result = encoder.encode("hello")
        assert result == "hello"

    def test_encode_string_with_special_chars(self):
        """Test encoding string with special characters."""
        encoder = ToonEncoder()
        result = encoder.encode("hello,world")
        assert result == '"hello,world"'


class TestToonEncoderEncodeDict:
    """Tests for encoding dictionaries."""

    def test_encode_empty_dict(self):
        """Test encoding empty dictionary."""
        encoder = ToonEncoder()
        result = encoder.encode({})
        # Empty dict returns empty string
        assert result == ""

    def test_encode_simple_dict(self):
        """Test encoding simple dictionary."""
        encoder = ToonEncoder()
        result = encoder.encode({"name": "test", "value": 42})
        lines = result.split("\n")
        assert "name: test" in lines
        assert "value: 42" in lines

    def test_encode_nested_dict(self):
        """Test encoding nested dictionary."""
        encoder = ToonEncoder()
        result = encoder.encode({"outer": {"inner": "value"}})
        lines = result.split("\n")
        assert "outer:" in lines
        assert "  inner: value" in lines

    def test_encode_dict_with_list(self):
        """Test encoding dictionary with list value."""
        encoder = ToonEncoder()
        result = encoder.encode({"items": [1, 2, 3]})
        lines = result.split("\n")
        assert "items: [1,2,3]" in lines


class TestToonEncoderEncodeList:
    """Tests for encoding lists."""

    def test_encode_empty_list(self):
        """Test encoding empty list."""
        encoder = ToonEncoder()
        result = encoder.encode([])
        assert result == "[]"

    def test_encode_simple_list(self):
        """Test encoding simple list."""
        encoder = ToonEncoder()
        result = encoder.encode([1, 2, 3])
        assert result == "[1,2,3]"

    def test_encode_list_with_tabs(self):
        """Test encoding list with tab delimiter."""
        encoder = ToonEncoder(use_tabs=True)
        result = encoder.encode([1, 2, 3])
        assert result == "[1\t2\t3]"

    def test_encode_nested_list(self):
        """Test encoding nested list."""
        encoder = ToonEncoder()
        result = encoder.encode([[1, 2], [3, 4]])
        assert result == "[[1,2],[3,4]]"


class TestToonEncoderEncodeArrayTable:
    """Tests for encoding arrays as tables."""

    def test_encode_homogeneous_dict_array(self):
        """Test encoding homogeneous array of dicts as table."""
        encoder = ToonEncoder()
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        result = encoder.encode(data)
        lines = result.split("\n")
        assert "[2]{name,age}:" in lines
        # Array table rows have indentation
        assert "  Alice,30" in lines
        assert "  Bob,25" in lines

    def test_encode_empty_array_table(self):
        """Test encoding empty array table."""
        encoder = ToonEncoder()
        result = encoder.encode([])
        assert result == "[]"

    def test_encode_array_table_with_tabs(self):
        """Test encoding array table with tab delimiter."""
        encoder = ToonEncoder(use_tabs=True)
        data = [{"a": 1, "b": 2}]
        result = encoder.encode(data)
        lines = result.split("\n")
        # Schema uses tab delimiter
        assert "[1]{a\tb}:" in lines
        # Array table rows have indentation
        assert "  1\t2" in lines


class TestToonEncoderEncodeString:
    """Tests for string encoding and escaping."""

    def test_encode_string_with_newline(self):
        """Test encoding string with newline."""
        encoder = ToonEncoder()
        result = encoder.encode("line1\nline2")
        assert result == '"line1\\nline2"'

    def test_encode_string_with_tab(self):
        """Test encoding string with tab."""
        encoder = ToonEncoder()
        result = encoder.encode("value1\tvalue2")
        assert result == '"value1\\tvalue2"'

    def test_encode_string_with_backslash(self):
        """Test encoding string with backslash."""
        encoder = ToonEncoder()
        result = encoder.encode("path\\to\\file")
        assert result == '"path\\\\to\\\\file"'

    def test_encode_string_with_quote(self):
        """Test encoding string with quote."""
        encoder = ToonEncoder()
        result = encoder.encode('say "hello"')
        assert result == '"say \\"hello\\""'

    def test_encode_string_with_braces(self):
        """Test encoding string with braces."""
        encoder = ToonEncoder()
        result = encoder.encode("test{value}")
        assert result == '"test{value}"'


class TestToonEncoderNormalizePath:
    """Tests for path normalization."""

    def test_normalize_windows_path_drive_letter(self):
        """Test normalization of Windows path with drive letter."""
        encoder = ToonEncoder()
        result = encoder.encode("C:\\path\\to\\file.txt")
        # Path is normalized and quoted because it contains special characters
        assert "C:/path/to/file.txt" in result

    def test_normalize_unc_path(self):
        """Test normalization of UNC path."""
        encoder = ToonEncoder()
        result = encoder.encode("\\\\server\\share\\file.txt")
        assert result == "//server/share/file.txt"

    def test_normalize_relative_path(self):
        """Test normalization of relative path."""
        encoder = ToonEncoder()
        result = encoder.encode(".\\relative\\path")
        assert result == "./relative/path"

    def test_normalize_parent_path(self):
        """Test normalization of parent path."""
        encoder = ToonEncoder()
        result = encoder.encode("..\\parent\\path")
        assert result == "../parent/path"

    def test_no_normalize_non_path_string(self):
        """Test that non-path strings are not normalized."""
        encoder = ToonEncoder()
        result = encoder.encode("backslash\\not\\path")
        # Should not normalize as it doesn't match path pattern
        # But backslashes are escaped in the output
        assert "backslash" in result and "not" in result and "path" in result

    def test_no_normalize_when_disabled(self):
        """Test that normalization is disabled when normalize_paths=False."""
        encoder = ToonEncoder(normalize_paths=False)
        result = encoder.encode("C:\\path\\to\\file.txt")
        # Backslashes are escaped but not normalized
        assert (
            "C:" in result
            and "path" in result
            and "to" in result
            and "file.txt" in result
        )


class TestToonEncoderCircularReference:
    """Tests for circular reference detection."""

    def test_detect_circular_reference_in_dict(self):
        """Test graceful degradation for circular reference in dictionary."""
        encoder = ToonEncoder(fallback_to_json=False)
        data = {"key": "value"}
        data["self"] = data  # Create circular reference

        # After bbe8a40: circular references return placeholder instead of raising
        result = encoder.encode(data)
        assert "[...]" in result  # Placeholder for circular reference

    def test_detect_circular_reference_in_list(self):
        """Test graceful degradation for circular reference in list."""
        encoder = ToonEncoder(fallback_to_json=False)
        data = [1, 2, 3]
        data.append(data)  # Create circular reference

        # After bbe8a40: circular references return placeholder instead of raising
        result = encoder.encode(data)
        assert "[...]" in result  # Placeholder for circular list reference

    def test_detect_circular_reference_static_method(self):
        """Test static method for circular reference detection."""
        data = {"key": "value"}
        data["self"] = data

        result = ToonEncoder.detect_circular_reference(data)
        assert result is True

    def test_no_circular_reference(self):
        """Test that non-circular structures are not flagged."""
        encoder = ToonEncoder()
        data = {"a": {"b": {"c": "value"}}}

        result = encoder.encode(data)
        assert "Circular reference" not in result


class TestToonEncoderErrorHandling:
    """Tests for error handling and fallback."""

    def test_fallback_to_json_on_error(self):
        """Test fallback to JSON on encoding error."""
        encoder = ToonEncoder(fallback_to_json=True)

        # Create a custom object that can't be encoded
        class CustomObject:
            pass

        obj = CustomObject()
        result = encoder.encode(obj)
        # Should fall back to JSON — result must be a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0  # ratchet: nondeterministic JSON fallback representation

    def test_no_fallback_raises_error(self):
        """Test that error is raised when fallback is disabled."""
        encoder = ToonEncoder(fallback_to_json=False, max_depth=1)

        # Create deeply nested structure that exceeds max depth
        data = {"level1": {"level2": {"level3": "value"}}}
        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(data)
        assert "Maximum nesting depth" in str(exc_info.value)

    def test_encode_safe_always_returns_string(self):
        """Test that encode_safe always returns a string."""
        encoder = ToonEncoder()

        class CustomObject:
            pass

        obj = CustomObject()
        result = encoder.encode_safe(obj)
        assert isinstance(result, str)


class TestToonEncoderEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_encode_with_indent(self):
        """Test encoding with indentation."""
        encoder = ToonEncoder()
        result = encoder.encode({"key": "value"}, indent=2)
        lines = result.split("\n")
        # Should have indentation
        assert any(line.startswith("    ") for line in lines)

    def test_encode_max_depth_exceeded(self):
        """Test that max depth limit is enforced."""
        encoder = ToonEncoder(max_depth=5, fallback_to_json=False)

        # Create deeply nested structure
        data = {}
        current = data
        for i in range(10):
            current[f"level{i}"] = {}
            current = current[f"level{i}"]

        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(data)
        assert "Maximum nesting depth" in str(exc_info.value)

    def test_encode_dict_in_list(self):
        """Test encoding dict inside list."""
        encoder = ToonEncoder()
        result = encoder.encode([{"a": 1}, {"b": 2}])
        # Non-homogeneous dict array (different keys) uses inline JSON
        # After Phase 3 optimization: only truly homogeneous arrays use Array Table
        assert "[{a:1},{b:2}]" in result or "[{" in result

    def test_encode_list_in_dict(self):
        """Test encoding list inside dict."""
        encoder = ToonEncoder()
        result = encoder.encode({"items": [1, 2, 3]})
        assert "items: [1,2,3]" in result


class TestToonEncoderConvenienceMethods:
    """Tests for convenience methods."""

    def test_encode_dict_method(self):
        """Test encode_dict convenience method."""
        encoder = ToonEncoder()
        result = encoder.encode_dict({"key": "value"})
        assert "key: value" in result

    def test_encode_list_method(self):
        """Test encode_list convenience method."""
        encoder = ToonEncoder()
        result = encoder.encode_list([1, 2, 3])
        assert result == "[1,2,3]"

    def test_encode_array_header_simple(self):
        """Test encode_array_header without schema."""
        encoder = ToonEncoder()
        result = encoder.encode_array_header(5)
        assert result == "[5]:"

    def test_encode_array_header_with_schema(self):
        """Test encode_array_header with schema."""
        encoder = ToonEncoder()
        result = encoder.encode_array_header(3, ["name", "age"])
        assert result == "[3]{name,age}:"

    def test_encode_array_table_method(self):
        """Test encode_array_table convenience method."""
        encoder = ToonEncoder()
        data = [{"a": 1, "b": 2}]
        result = encoder.encode_array_table(data)
        lines = result.split("\n")
        assert "[1]{a,b}:" in lines
        # Array table rows have indentation
        assert "  1,2" in lines


class TestToonEncoderCompactFormats:
    """Tests for compact format features."""

    def test_encode_tuple_in_array_table(self):
        """Test encoding tuple values in array table."""
        encoder = ToonEncoder()
        data = [{"pos": (10, 20), "name": "test"}]
        result = encoder.encode(data)
        result.split("\n")
        # Should have (a,b) annotation in schema
        assert "pos(a,b)" in result
        # Should have compact tuple format
        assert "(10,20)" in result

    def test_encode_dict_in_array_table(self):
        """Test encoding dict values in array table."""
        encoder = ToonEncoder()
        data = [{"meta": {"x": 1, "y": 2}, "name": "test"}]
        result = encoder.encode(data)
        result.split("\n")
        # Should have {keys} annotation in schema
        assert "meta{x,y}" in result
        # Should have compact dict format
        assert "(1,2)" in result


class TestToonEncoderEncodeValue:
    """Tests for encode_value method."""

    def test_encode_value_none(self):
        """Test encode_value with None."""
        encoder = ToonEncoder()
        result = encoder.encode_value(None)
        assert result == "null"

    def test_encode_value_bool(self):
        """Test encode_value with boolean."""
        encoder = ToonEncoder()
        assert encoder.encode_value(True) == "true"
        assert encoder.encode_value(False) == "false"

    def test_encode_value_number(self):
        """Test encode_value with number."""
        encoder = ToonEncoder()
        assert encoder.encode_value(42) == "42"
        assert encoder.encode_value(3.14) == "3.14"

    def test_encode_value_string(self):
        """Test encode_value with string."""
        encoder = ToonEncoder()
        result = encoder.encode_value("test")
        assert result == "test"

    def test_encode_value_dict_inline(self):
        """Test encode_value with inline dict."""
        encoder = ToonEncoder()
        result = encoder.encode_value({"a": 1, "b": 2})
        assert "{a:1,b:2}" in result

    def test_encode_value_list_inline(self):
        """Test encode_value with inline list."""
        encoder = ToonEncoder()
        result = encoder.encode_value([1, 2, 3])
        assert result == "[1,2,3]"


class TestToonEncoderInferSchema:
    """Tests for schema inference."""

    def test_infer_schema_from_items(self):
        """Test inferring schema from array items."""
        encoder = ToonEncoder()
        data = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        schema = encoder._infer_schema(data)
        assert set(schema) == {"name", "age"}

    def test_infer_schema_empty(self):
        """Test inferring schema from empty array."""
        encoder = ToonEncoder()
        schema = encoder._infer_schema([])
        assert schema == []


class TestToonEncoderEncodeInlineDict:
    """Tests for inline dict encoding."""

    def test_encode_inline_dict_simple(self):
        """Test encoding simple inline dict."""
        encoder = ToonEncoder()
        result = encoder._encode_inline_dict({"a": 1, "b": 2}, set())
        assert "{a:1,b:2}" in result

    def test_encode_inline_dict_empty(self):
        """Test encoding empty inline dict."""
        encoder = ToonEncoder()
        result = encoder._encode_inline_dict({}, set())
        assert result == "{}"

    def test_encode_inline_dict_nested(self):
        """Test encoding nested inline dict."""
        encoder = ToonEncoder()
        result = encoder._encode_inline_dict({"outer": {"inner": "value"}}, set())
        assert "{outer:{inner:value}}" in result


class TestToonEncoderEncodeSimpleList:
    """Tests for simple list encoding."""

    def test_encode_simple_list_empty(self):
        """Test encoding empty simple list."""
        encoder = ToonEncoder()
        result = encoder._encode_simple_list([], set())
        assert result == "[]"

    def test_encode_simple_list_primitives(self):
        """Test encoding list of primitives."""
        encoder = ToonEncoder()
        result = encoder._encode_simple_list([1, 2, 3], set())
        assert result == "[1,2,3]"

    def test_encode_simple_list_nested(self):
        """Test encoding list with nested lists."""
        encoder = ToonEncoder()
        result = encoder._encode_simple_list([[1, 2], [3, 4]], set())
        assert "[[1,2],[3,4]]" in result


class TestToonEncoderComplexStructures:
    """Tests for complex nested structures."""

    def test_encode_deeply_nested_dict(self):
        """Test encoding deeply nested dictionary."""
        encoder = ToonEncoder()
        data = {"level1": {"level2": {"level3": {"level4": "value"}}}}
        result = encoder.encode(data)
        lines = result.split("\n")
        assert "level1:" in lines
        assert "  level2:" in lines
        assert "    level3:" in lines
        assert "      level4: value" in lines

    def test_encode_mixed_structure(self):
        """Test encoding mixed structure with dicts and lists."""
        encoder = ToonEncoder()
        data = {
            "name": "test",
            "items": [1, 2, 3],
            "nested": {"key": "value"},
        }
        result = encoder.encode(data)
        assert "name: test" in result
        assert "items: [1,2,3]" in result
        assert "nested:" in result
        assert "  key: value" in result


class TestToonEncoderSpecialCharacters:
    """Tests for handling special characters."""

    def test_encode_string_with_colon(self):
        """Test encoding string with colon."""
        encoder = ToonEncoder()
        result = encoder.encode("key:value")
        assert result == '"key:value"'

    def test_encode_string_with_brackets(self):
        """Test encoding string with brackets."""
        encoder = ToonEncoder()
        result = encoder.encode("test[value]")
        assert result == '"test[value]"'

    def test_encode_string_with_carriage_return(self):
        """Test encoding string with carriage return."""
        encoder = ToonEncoder()
        result = encoder.encode("line1\rline2")
        assert result == '"line1\\rline2"'

    def test_encode_string_with_all_special_chars(self):
        """Test encoding string with multiple special characters."""
        encoder = ToonEncoder()
        result = encoder.encode('test: value\nwith\t"quotes"')
        assert result.startswith('"')
        assert result.endswith('"')


class TestToonEncoderLongFlatStringList:
    """Regression — M9: long flat ``list[str]`` rendering.

    Round-14b found that ``safe_to_edit(output_format='toon')`` rendered
    ``downstream_files: [a,b,c,...]`` as a single long inline blob that
    downstream tooling truncated mid-content. The encoder now switches
    to a single-column TOON array-table once the list exceeds the
    threshold (5 items).
    """

    def test_long_path_list_renders_as_array_table(self):
        encoder = ToonEncoder()
        data = {
            "downstream_files": [
                "start_mcp_server.py",
                "tests/test_a.py",
                "tests/test_b.py",
                "tests/test_c.py",
                "tests/test_d.py",
                "tests/test_e.py",
                "tests/test_f.py",
            ],
        }
        result = encoder.encode(data)
        lines = result.split("\n")
        # Header is on its own line, followed by the array-table marker.
        assert "downstream_files:" in lines
        assert "  [7]{path}:" in lines
        # Each path lives on its own line — one item per line.
        assert "    start_mcp_server.py" in lines
        assert "    tests/test_a.py" in lines
        assert "    tests/test_f.py" in lines
        # Inline form should NOT appear.
        assert "downstream_files: [" not in result

    def test_short_path_list_stays_inline(self):
        # Lists at or below the threshold (5) keep the inline form to
        # avoid the table-header overhead on values that fit on one line.
        encoder = ToonEncoder()
        data = {"tags": ["urgent", "review", "docs"]}
        result = encoder.encode(data)
        assert "tags: [urgent,review,docs]" in result.split("\n")

    def test_threshold_boundary_inclusive_at_five(self):
        encoder = ToonEncoder()
        data = {"paths": ["a.py", "b.py", "c.py", "d.py", "e.py"]}
        result = encoder.encode(data)
        # Exactly 5 items — still inline.
        assert "paths: [a.py,b.py,c.py,d.py,e.py]" in result.split("\n")

    def test_threshold_boundary_table_at_six(self):
        encoder = ToonEncoder()
        data = {"paths": ["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"]}
        result = encoder.encode(data)
        lines = result.split("\n")
        assert "paths:" in lines
        assert "  [6]{path}:" in lines

    def test_mixed_list_str_and_dict_unchanged(self):
        # list[dict] keeps its existing array-table behavior (sanity check
        # the M9 change didn't reroute mixed-type list rendering).
        encoder = ToonEncoder()
        data = {
            "risk_factors": [
                {"factor": "size", "detail": "large", "severity": "med"},
                {"factor": "churn", "detail": "50%", "severity": "low"},
            ],
        }
        result = encoder.encode(data)
        lines = result.split("\n")
        assert "risk_factors:" in lines
        assert "  [2]{factor,detail,severity}:" in lines
        assert "    size,large,med" in lines

    def test_non_string_list_falls_back_to_inline(self):
        # Long list of ints stays inline — the table rule is gated on
        # all items being strings.
        encoder = ToonEncoder()
        data = {"counts": [1, 2, 3, 4, 5, 6, 7, 8]}
        result = encoder.encode(data)
        assert "counts: [1,2,3,4,5,6,7,8]" in result.split("\n")

    def test_column_name_picked_from_key_suffix(self):
        encoder = ToonEncoder()
        # paths/files keys → "path" column
        for key in ("downstream_files", "paths", "test_paths"):
            data = {key: [f"item_{i}" for i in range(7)]}
            result = encoder.encode(data)
            assert "  [7]{path}:" in result.split("\n"), (
                f"Expected 'path' column for key={key}, got:\n{result}"
            )

    def test_column_name_falls_back_to_item(self):
        encoder = ToonEncoder()
        # Unknown suffix → "item" fallback
        data = {"misc_things": [f"x_{i}" for i in range(7)]}
        result = encoder.encode(data)
        assert "  [7]{item}:" in result.split("\n")

    def test_empty_string_list_stays_empty(self):
        encoder = ToonEncoder()
        # Empty list — no rendering change regardless of threshold.
        data = {"paths": []}
        result = encoder.encode(data)
        assert "paths: []" in result.split("\n")


# ---------------------------------------------------------------------------
# Tests migrated from test_toon_coverage_boost.py
# ---------------------------------------------------------------------------


from tree_sitter_analyzer.formatters.toon_encoder import (  # noqa: E402
    _Task,
    _TaskType,
)


class TestToonEncoderArrayTableShapes:
    """Behavioral tests for array table encoding shapes."""

    def test_encode_array_table_with_tuple_values(self):
        encoder = ToonEncoder()
        items = [{"name": "test", "range": (1, 10)}]
        result = encoder.encode_array_table(items)
        assert "range(a,b)" in result
        assert "(1,10)" in result

    def test_encode_array_table_with_dict_values(self):
        encoder = ToonEncoder()
        items = [{"name": "test", "meta": {"start": 1, "end": 2}}]
        result = encoder.encode_array_table(items)
        assert "meta{start,end}" in result

    def test_encode_list_with_nested_dicts_produces_array_table(self):
        encoder = ToonEncoder()
        data = [{"a": 1}, {"a": 2}]
        result = encoder.encode_list(data)
        assert "[2]{a}:" in result

    def test_encode_with_tabs_delimiter(self):
        encoder = ToonEncoder(use_tabs=True)
        assert encoder.delimiter == "\t"
        items = [{"a": 1, "b": 2}]
        result = encoder.encode_array_table(items)
        assert "\t" in result


class TestToonEncoderHandleListItem:
    """Behavioral tests for _handle_list_item."""

    def test_handle_list_item_with_dict_pushes_dict_task(self):
        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, {"key": "value"}, indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(stack) == 1
        assert stack[0].task_type == _TaskType.ENCODE_DICT_START

    def test_handle_list_item_with_list_pushes_list_task(self):
        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, [1, 2, 3], indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(stack) == 1
        assert stack[0].task_type == _TaskType.ENCODE_LIST_START

    def test_handle_list_item_with_primitive_adds_to_output(self):
        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_ITEM, "hello", indent=1)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_item(task, stack, output, seen_ids)
        assert len(output) == 1
        assert "hello" in output[0]


class TestToonEncoderHandleListStart:
    """Behavioral tests for _handle_list_start."""

    def test_handle_list_start_empty_list_outputs_empty_brackets(self):
        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_LIST_START, [], indent=0)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_list_start(task, stack, output, seen_ids)
        assert output == ["[]"]

    def test_handle_list_start_circular_reference_outputs_placeholder(self):
        encoder = ToonEncoder()
        data = [1, 2]
        obj_id = id(data)
        task = _Task(_TaskType.ENCODE_LIST_START, data, indent=0)
        stack: list[_Task] = []
        output: list[str] = []
        seen_ids: set[int] = {obj_id}

        encoder._handle_list_start(task, stack, output, seen_ids)
        result = "".join(output)
        assert "[...]" in result


class TestToonEncoderHandleArrayTable:
    """Behavioral tests for _handle_array_table."""

    def test_handle_array_table_empty_outputs_empty_brackets(self):
        encoder = ToonEncoder()
        task = _Task(_TaskType.ENCODE_ARRAY_TABLE, [], indent=0)
        output: list[str] = []
        seen_ids: set[int] = set()

        encoder._handle_array_table(task, output, seen_ids)
        assert output == ["[]"]

    def test_handle_array_table_circular_reference_outputs_placeholder(self):
        encoder = ToonEncoder()
        data = [{"key": 1}]
        obj_id = id(data)
        task = _Task(_TaskType.ENCODE_ARRAY_TABLE, data, indent=0)
        output: list[str] = []
        seen_ids: set[int] = {obj_id}

        encoder._handle_array_table(task, output, seen_ids)
        result = "".join(output)
        assert "[...]" in result
