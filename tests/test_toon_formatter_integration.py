#!/usr/bin/env python3
"""
Tests for ToonFormatter integration with OutputManager.

Validates the unified format() interface and proper dispatching
between format_analysis_result and format_mcp_response methods.
"""

import pytest

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncoder
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter
from tree_sitter_analyzer.output_manager import OutputManager


class TestToonEncoder:
    """Test ToonEncoder basic functionality."""

    def test_encode_value_primitives(self):
        """Test encoding of primitive values."""
        encoder = ToonEncoder()

        assert encoder.encode_value(None) == "null"
        assert encoder.encode_value(True) == "true"
        assert encoder.encode_value(False) == "false"
        assert encoder.encode_value(42) == "42"
        assert encoder.encode_value(3.14) == "3.14"
        assert encoder.encode_value("hello") == "hello"

    def test_encode_value_with_special_chars(self):
        """Test encoding of strings with special characters."""
        encoder = ToonEncoder()

        # Strings with special chars should be quoted
        assert encoder.encode_value("hello,world") == '"hello,world"'
        assert encoder.encode_value("key:value") == '"key:value"'

    def test_string_escaping_comprehensive(self):
        """Test complete string escaping according to TOON specification."""
        encoder = ToonEncoder()

        # Test individual escape sequences
        assert encoder.encode_value("line1\nline2") == '"line1\\nline2"'
        assert encoder.encode_value("tab\there") == '"tab\\there"'
        assert encoder.encode_value("return\rchar") == '"return\\rchar"'
        assert encoder.encode_value('quoted"text') == '"quoted\\"text"'
        assert encoder.encode_value("back\\slash") == '"back\\\\slash"'

    def test_string_escaping_combinations(self):
        """Test escaping of complex string combinations."""
        encoder = ToonEncoder()

        # Multiple special characters
        assert encoder.encode_value("a\nb\tc") == '"a\\nb\\tc"'
        assert encoder.encode_value('say "hello\nworld"') == '"say \\"hello\\nworld\\""'

        # Backslash before special chars (order matters)
        assert encoder.encode_value("\\n") == '"\\\\n"'  # Literal backslash-n
        assert encoder.encode_value("\\\n") == '"\\\\\\n"'  # Backslash + newline

    def test_string_no_escaping_needed(self):
        """Test strings that don't need quotes or escaping."""
        encoder = ToonEncoder()

        # Simple strings without special characters
        assert encoder.encode_value("hello") == "hello"
        assert encoder.encode_value("test123") == "test123"
        assert encoder.encode_value("simple_value") == "simple_value"

    def test_string_escaping_prevents_format_corruption(self):
        """Test that escaping prevents TOON format corruption."""
        encoder = ToonEncoder()

        # These would break TOON structure without proper escaping
        data = {
            "message": "Error:\nStack trace here",
            "path": "C:\\Users\\test\\file.txt",
            "content": 'He said "Hello"',
        }

        result = encoder.encode_dict(data)

        # Verify no literal newlines in output (would break line structure)
        lines = result.split("\n")

        # Should have exactly 3 lines (one per key)
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}: {lines}"

        # Each line should start with a key
        assert lines[0].startswith("message:")
        assert lines[1].startswith("path:")
        assert lines[2].startswith("content:")

        # Verify escape sequences are present
        assert "\\n" in result  # Escaped newline
        assert (
            "\\\\Users" in result or "\\\\\\\\Users" in result
        )  # Escaped backslash (Windows path)
        assert '\\"Hello\\"' in result  # Escaped quotes

    def test_encode_dict_simple(self):
        """Test encoding of simple dictionary."""
        encoder = ToonEncoder()

        data = {"name": "test", "count": 42, "active": True}

        result = encoder.encode_dict(data)

        assert "name: test" in result
        assert "count: 42" in result
        assert "active: true" in result

    def test_encode_dict_nested(self):
        """Test encoding of nested dictionary."""
        encoder = ToonEncoder()

        data = {"user": {"name": "Alice", "age": 30}, "active": True}

        result = encoder.encode_dict(data)

        assert "user:" in result
        assert "name: Alice" in result
        assert "age: 30" in result
        assert "active: true" in result

    def test_encode_list_simple(self):
        """Test encoding of simple list."""
        encoder = ToonEncoder()

        items = [1, 2, 3, 4, 5]
        result = encoder.encode_list(items)

        assert result == "[1,2,3,4,5]"

    def test_encode_array_table(self):
        """Test encoding of homogeneous array as table."""
        encoder = ToonEncoder()

        items = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]

        result = encoder.encode_array_table(items, schema=["name", "age"])

        assert "[2]{name,age}:" in result
        assert "Alice,30" in result
        assert "Bob,25" in result

    def test_encode_array_table_infer_schema(self):
        """Test array table with schema inference."""
        encoder = ToonEncoder()

        items = [{"id": 1, "status": "active"}, {"id": 2, "status": "inactive"}]

        result = encoder.encode_array_table(items)

        assert "[2]{id,status}:" in result
        assert "1,active" in result
        assert "2,inactive" in result


class TestToonFormatter:
    """Test ToonFormatter functionality."""

    def test_formatter_initialization(self):
        """Test ToonFormatter initialization."""
        formatter = ToonFormatter()

        assert formatter.use_tabs is False
        assert formatter.compact_arrays is True
        assert formatter.include_metadata is True
        assert isinstance(formatter.encoder, ToonEncoder)

    def test_formatter_with_tabs(self):
        """Test ToonFormatter with tab delimiters."""
        formatter = ToonFormatter(use_tabs=True)

        assert formatter.use_tabs is True
        assert formatter.encoder.use_tabs is True
        assert formatter.encoder.delimiter == "\t"

    def test_format_dict_generic(self):
        """Test format() method with generic dictionary."""
        formatter = ToonFormatter()

        data = {"file": "test.py", "lines": 100, "functions": 5}

        result = formatter.format(data)

        assert "file: test.py" in result
        assert "lines: 100" in result
        assert "functions: 5" in result

    def test_format_mcp_response(self):
        """Test format() method with MCP response structure."""
        formatter = ToonFormatter()

        # MCP response typically has 'content' or 'data' fields
        mcp_response = {
            "content": [{"type": "text", "text": "Analysis complete"}],
            "metadata": {"tool": "analyze_code_scale", "duration_ms": 123},
        }

        result = formatter.format(mcp_response)

        # Should detect MCP structure and format accordingly
        assert "content:" in result or "metadata:" in result

    def test_format_structure(self):
        """Test format_structure method."""
        formatter = ToonFormatter()

        analysis_result = {
            "file_path": "test.java",
            "language": "java",
            "classes": [{"name": "TestClass", "methods": 5}],
        }

        result = formatter.format_structure(analysis_result)

        assert "file_path: test.java" in result
        assert "language: java" in result

    def test_is_mcp_response_detection(self):
        """Test MCP response detection logic."""
        formatter = ToonFormatter()

        # Should detect MCP responses
        assert formatter._is_mcp_response({"content": []})
        assert formatter._is_mcp_response({"data": {}})
        assert formatter._is_mcp_response({"metadata": {}})

        # Should not detect regular dicts
        assert not formatter._is_mcp_response({"file_path": "test.py"})
        assert not formatter._is_mcp_response({"name": "test"})


class TestOutputManagerIntegration:
    """Test OutputManager integration with ToonFormatter."""

    def test_output_manager_formatter_registry(self):
        """Test OutputManager initializes formatter registry."""
        manager = OutputManager()

        assert hasattr(manager, "_formatter_registry")
        assert isinstance(manager._formatter_registry, dict)
        assert "json" in manager._formatter_registry
        assert "toon" in manager._formatter_registry

    def test_output_manager_toon_format(self, capsys):
        """Test OutputManager.data() with TOON format."""
        manager = OutputManager(output_format="toon")

        data = {"file": "test.py", "lines": 100}

        manager.data(data)

        captured = capsys.readouterr()
        assert "file: test.py" in captured.out
        assert "lines: 100" in captured.out

    def test_output_manager_json_format(self, capsys):
        """Test OutputManager.data() with JSON format."""
        manager = OutputManager(output_format="json")

        data = {"test": "value"}

        manager.data(data)

        captured = capsys.readouterr()
        assert '"test"' in captured.out
        assert '"value"' in captured.out

    def test_output_manager_format_override(self, capsys):
        """Test format_type parameter overrides default."""
        manager = OutputManager(output_format="json")

        data = {"key": "value"}

        # Override to use TOON
        manager.data(data, format_type="toon")

        captured = capsys.readouterr()
        assert "key: value" in captured.out

    def test_formatter_has_format_method(self):
        """Test that ToonFormatter implements format() method."""
        formatter = ToonFormatter()

        assert hasattr(formatter, "format")
        assert callable(formatter.format)

    def test_formatter_format_method_signature(self):
        """Test format() method accepts Any and returns str."""
        formatter = ToonFormatter()

        # Should accept dict
        result = formatter.format({"test": "data"})
        assert isinstance(result, str)

        # Should accept list
        result = formatter.format([1, 2, 3])
        assert isinstance(result, str)

        # Should accept primitive
        result = formatter.format("test string")
        assert isinstance(result, str)

    def test_output_manager_fallback_behavior(self, capsys):
        """Test OutputManager fallback when formatter not available."""
        manager = OutputManager(output_format="unsupported_format")

        data = {"test": "data"}

        # Should fall back to JSON
        manager.data(data)

        captured = capsys.readouterr()
        # Should output something (either JSON or formatted data)
        assert len(captured.out) > 0


class TestFormatterProtocolCompliance:
    """Test that all formatters comply with the Formatter protocol."""

    def test_toon_formatter_protocol(self):
        """Test ToonFormatter implements all BaseFormatter methods."""
        formatter = ToonFormatter()

        # Required methods from BaseFormatter
        assert hasattr(formatter, "format")
        assert hasattr(formatter, "format_summary")
        assert hasattr(formatter, "format_structure")
        assert hasattr(formatter, "format_advanced")
        assert hasattr(formatter, "format_table")

        # All methods should be callable
        assert callable(formatter.format)
        assert callable(formatter.format_summary)
        assert callable(formatter.format_structure)
        assert callable(formatter.format_advanced)
        assert callable(formatter.format_table)

    def test_formatter_unified_interface(self):
        """Test unified format() method works as dispatcher."""
        formatter = ToonFormatter()

        # Test with different data types
        dict_data = {"key": "value"}
        result = formatter.format(dict_data)
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify it produces TOON-like output
        assert ":" in result or "{" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
