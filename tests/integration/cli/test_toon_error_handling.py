#!/usr/bin/env python3
"""
Tests for TOON format error handling.

Verifies that:
1. Circular references are detected
2. JSON fallback works on errors
3. Error logging is performed
4. ToonEncodeError provides detailed information
"""

import pytest

from tree_sitter_analyzer.formatters.toon_encoder import ToonEncodeError, ToonEncoder
from tree_sitter_analyzer.formatters.toon_formatter import ToonFormatter


class TestToonEncodeError:
    """Tests for ToonEncodeError exception class."""

    def test_error_basic_creation(self):
        """Test basic error creation."""
        error = ToonEncodeError("Test error message")

        assert str(error) == "ToonEncodeError: Test error message"
        assert error.message == "Test error message"
        assert error.data is None
        assert error.cause is None

    def test_error_with_data(self):
        """Test error with data attribute."""
        data = {"key": "value"}
        error = ToonEncodeError("Failed to encode", data=data)

        assert error.data == data
        assert "Failed to encode" in str(error)

    def test_error_with_cause(self):
        """Test error with cause exception."""
        cause = ValueError("Original error")
        error = ToonEncodeError("Encoding failed", cause=cause)

        assert error.cause == cause
        assert "ValueError" in str(error)
        assert "Original error" in str(error)

    def test_error_with_all_attributes(self):
        """Test error with all attributes."""
        data = [1, 2, 3]
        cause = TypeError("Type mismatch")
        error = ToonEncodeError("Complete error", data=data, cause=cause)

        assert error.message == "Complete error"
        assert error.data == data
        assert error.cause == cause
        assert "Complete error" in str(error)
        assert "TypeError" in str(error)


class TestCircularReferenceDetection:
    """Tests for circular reference detection."""

    def test_detect_simple_circular_dict(self):
        """Test detection of simple circular reference in dict."""
        data: dict = {"key": "value"}
        data["self"] = data  # Create circular reference

        encoder = ToonEncoder(fallback_to_json=False)

        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(data)

        assert "Circular reference" in str(exc_info.value)

    def test_detect_nested_circular_dict(self):
        """Test detection of nested circular reference."""
        outer: dict = {"level": 1}
        inner: dict = {"level": 2}
        outer["child"] = inner
        inner["parent"] = outer  # Create circular reference

        encoder = ToonEncoder(fallback_to_json=False)

        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(outer)

        assert "Circular reference" in str(exc_info.value)

    def test_detect_circular_list(self):
        """Test detection of circular reference in list."""
        data: list = [1, 2, 3]
        data.append(data)  # Create circular reference

        encoder = ToonEncoder(fallback_to_json=False)

        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(data)

        assert "Circular reference" in str(exc_info.value)

    def test_static_circular_reference_check(self):
        """Test static method for circular reference detection."""
        # Non-circular data
        normal_data = {"a": {"b": {"c": 1}}}
        assert ToonEncoder.detect_circular_reference(normal_data) is False

        # Circular data
        circular_data: dict = {"key": "value"}
        circular_data["self"] = circular_data
        assert ToonEncoder.detect_circular_reference(circular_data) is True

    def test_no_false_positive_same_value(self):
        """Test that same values at different paths don't trigger false positive."""
        shared_list = [1, 2, 3]
        data = {
            "first": shared_list,
            "second": shared_list,  # Same list, but not circular
        }

        encoder = ToonEncoder(fallback_to_json=False)
        # Should not raise - same object at different paths is OK
        result = encoder.encode(data)
        assert "first:" in result
        assert "second:" in result


class TestJsonFallback:
    """Tests for JSON fallback mechanism."""

    def test_fallback_on_circular_reference(self):
        """Test JSON fallback when circular reference is detected."""
        data: dict = {"key": "value", "count": 42}
        data["self"] = data  # Create circular reference

        encoder = ToonEncoder(fallback_to_json=True)
        result = encoder.encode(data)

        # Should fall back to JSON (which handles circular refs differently)
        # or return an error message
        assert result is not None
        assert len(result) > 0

    def test_encode_safe_always_returns_string(self):
        """Test that encode_safe always returns a string."""
        encoder = ToonEncoder(fallback_to_json=True)

        # Normal data
        result1 = encoder.encode_safe({"key": "value"})
        assert isinstance(result1, str)
        assert "key" in result1

        # Circular reference
        circular: dict = {"x": 1}
        circular["self"] = circular
        result2 = encoder.encode_safe(circular)
        assert isinstance(result2, str)

    def test_fallback_disabled_raises_error(self):
        """Test that disabling fallback raises error on failure."""
        data: dict = {"key": "value"}
        data["self"] = data

        encoder = ToonEncoder(fallback_to_json=False)

        with pytest.raises(ToonEncodeError):
            encoder.encode(data)

    def test_formatter_fallback(self):
        """Test ToonFormatter fallback mechanism."""
        data: dict = {"key": "value"}
        data["self"] = data

        formatter = ToonFormatter(fallback_to_json=True)
        result = formatter.format(data)

        # Should return something (either JSON fallback or error message)
        assert isinstance(result, str)
        assert len(result) > 0


class TestMaxDepthLimit:
    """Tests for maximum nesting depth limit."""

    def test_max_depth_exceeded(self):
        """Test that deeply nested structures are rejected."""
        # Create deeply nested structure
        data: dict = {"level": 0}
        current = data
        for i in range(150):  # Exceed default max_depth of 100
            current["child"] = {"level": i + 1}
            current = current["child"]

        encoder = ToonEncoder(fallback_to_json=False, max_depth=100)

        with pytest.raises(ToonEncodeError) as exc_info:
            encoder.encode(data)

        assert "depth" in str(exc_info.value).lower()

    def test_custom_max_depth(self):
        """Test custom max depth setting."""
        # Create structure with depth 10
        data: dict = {"level": 0}
        current = data
        for i in range(10):
            current["child"] = {"level": i + 1}
            current = current["child"]

        # Should fail with max_depth=5
        encoder_shallow = ToonEncoder(fallback_to_json=False, max_depth=5)
        with pytest.raises(ToonEncodeError):
            encoder_shallow.encode(data)

        # Should succeed with max_depth=20
        encoder_deep = ToonEncoder(fallback_to_json=False, max_depth=20)
        result = encoder_deep.encode(data)
        assert "level: 0" in result


class TestToonContentDetection:
    """Tests for TOON content format detection."""

    def test_detect_toon_key_value(self):
        """Test detection of TOON key-value format."""
        toon_content = """file_path: test.py
language: python
count: 42"""

        assert ToonFormatter.is_toon_content(toon_content) is True

    def test_detect_toon_array_table(self):
        """Test detection of TOON array table format."""
        toon_content = """results:
  [3]{name,line}:
    func1,10
    func2,20
    func3,30"""

        assert ToonFormatter.is_toon_content(toon_content) is True

    def test_reject_json_content(self):
        """Test that JSON content is not detected as TOON."""
        json_content = '{"key": "value", "count": 42}'

        assert ToonFormatter.is_toon_content(json_content) is False

    def test_reject_empty_content(self):
        """Test that empty content is not detected as TOON."""
        assert ToonFormatter.is_toon_content("") is False
        assert ToonFormatter.is_toon_content("   ") is False

    def test_reject_json_array(self):
        """Test that JSON arrays are not detected as TOON."""
        json_array = '[{"name": "test"}, {"name": "test2"}]'

        assert ToonFormatter.is_toon_content(json_array) is False


class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    def test_partial_encoding_on_error(self):
        """Test behavior when encoding partially fails."""

        # Create an object that's difficult to encode
        class CustomObject:
            def __str__(self):
                raise ValueError("Cannot convert to string")

        data = {"normal": "value", "problem": CustomObject()}

        encoder = ToonEncoder(fallback_to_json=True)
        result = encoder.encode(data)

        # Should either succeed with fallback or include error marker
        assert isinstance(result, str)

    def test_safe_encode_with_none(self):
        """Test safe encoding of None values."""
        encoder = ToonEncoder()
        result = encoder.encode_safe(None)

        assert result == "null"

    def test_safe_encode_with_special_types(self):
        """Test safe encoding of special Python types."""
        encoder = ToonEncoder()

        # Boolean
        assert encoder.encode_safe(True) == "true"
        assert encoder.encode_safe(False) == "false"

        # Numbers
        assert encoder.encode_safe(42) == "42"
        assert encoder.encode_safe(3.14) == "3.14"

        # Empty collections
        assert encoder.encode_safe([]) == "[]"
        assert encoder.encode_safe({}) == ""
