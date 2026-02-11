"""
Test TOON formatter implementation.

Following TDD: Write tests FIRST to define the contract.
This is T3.1: TOON Formatter

TOON (Token-Oriented Object Notation) is a YAML-like format optimized for LLM consumption.
Goals:
- 50%+ token reduction compared to JSON
- Maintain human readability
- Support primitive values, dictionaries, arrays, and compact array tables
"""


class TestToonFormatterBasics:
    """Test basic TOON formatter functionality."""

    def test_formatter_can_be_imported(self):
        """Test that ToonFormatter can be imported."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        assert ToonFormatter is not None

    def test_formatter_initialization(self):
        """Test creating a formatter instance."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        assert formatter is not None

    def test_format_returns_string(self):
        """Test that format() returns a string."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format({"key": "value"})

        assert isinstance(result, str)


class TestToonPrimitiveValues:
    """Test TOON encoding of primitive values."""

    def test_encode_null(self):
        """Test encoding None/null."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format(None)

        assert result.strip() == "null"

    def test_encode_boolean_true(self):
        """Test encoding True."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format(True)

        assert result.strip() == "true"

    def test_encode_boolean_false(self):
        """Test encoding False."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format(False)

        assert result.strip() == "false"

    def test_encode_number(self):
        """Test encoding numbers."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        assert formatter.format(42).strip() == "42"
        assert formatter.format(3.14).strip() == "3.14"
        assert formatter.format(-100).strip() == "-100"

    def test_encode_simple_string(self):
        """Test encoding simple strings (unquoted)."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format("hello")

        assert result.strip() == "hello"


class TestToonDictionaries:
    """Test TOON encoding of dictionaries."""

    def test_encode_simple_dict(self):
        """Test encoding simple dictionary."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = {"name": "example", "count": 42, "active": True}

        result = formatter.format(data)

        # Should contain key-value pairs
        assert "name: example" in result
        assert "count: 42" in result
        assert "active: true" in result

    def test_encode_nested_dict(self):
        """Test encoding nested dictionaries with indentation."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = {
            "file": "sample.py",
            "metadata": {"language": "python", "version": "3.11"},
            "statistics": {"lines": 100, "methods": 5},
        }

        result = formatter.format(data)

        # Should have proper indentation
        assert "file: sample.py" in result
        assert "metadata:" in result
        assert "  language: python" in result
        assert "  version: 3.11" in result or '  version: "3.11"' in result
        assert "statistics:" in result
        assert "  lines: 100" in result
        assert "  methods: 5" in result


class TestToonArrays:
    """Test TOON encoding of arrays."""

    def test_encode_simple_array(self):
        """Test encoding simple arrays with bracket notation."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = [1, 2, 3, 4, 5]

        result = formatter.format(data)

        assert "[1,2,3,4,5]" in result

    def test_encode_string_array(self):
        """Test encoding array of strings."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = ["python", "typescript", "rust"]

        result = formatter.format(data)

        assert "[python,typescript,rust]" in result


class TestToonArrayTables:
    """Test TOON compact array table format."""

    def test_encode_array_of_dicts_as_table(self):
        """Test encoding homogeneous array of dicts as compact table."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = {
            "methods": [
                {"name": "init", "visibility": "public", "lines": "1-10"},
                {"name": "process", "visibility": "public", "lines": "12-45"},
                {"name": "validate", "visibility": "private", "lines": "47-60"},
            ]
        }

        result = formatter.format(data)

        # Should contain compact table format
        # [3]{name,visibility,lines}:
        #   init,public,1-10
        #   process,public,12-45
        #   validate,private,47-60
        assert "[3]" in result or "methods:" in result
        assert "name" in result
        assert "visibility" in result
        assert "init" in result
        assert "process" in result
        assert "validate" in result


class TestToonComplexStructures:
    """Test TOON encoding of complex nested structures."""

    def test_encode_analysis_result(self):
        """Test encoding a typical analysis result."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = {
            "file_path": "example.py",
            "language": "python",
            "functions": [
                {"name": "hello", "parameters": [], "line_start": 1, "line_end": 3},
                {"name": "add", "parameters": ["a", "b"], "line_start": 5, "line_end": 7},
            ],
            "metadata": {
                "total_functions": 2,
                "total_classes": 0,
            },
        }

        result = formatter.format(data)

        # Should be compact and readable
        assert "file_path:" in result or "file_path :" in result
        assert "example.py" in result
        assert "language:" in result or "language :" in result
        assert "python" in result
        assert "functions:" in result or "functions :" in result
        assert "metadata:" in result or "metadata :" in result


class TestToonTokenReduction:
    """Test TOON token reduction goals."""

    def test_token_reduction_vs_json(self):
        """Test that TOON format is significantly shorter than JSON."""
        import json

        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        data = {
            "methods": [
                {"name": "init", "visibility": "public", "lines": "1-10"},
                {"name": "process", "visibility": "public", "lines": "12-45"},
                {"name": "validate", "visibility": "private", "lines": "47-60"},
                {"name": "cleanup", "visibility": "public", "lines": "62-70"},
            ]
        }

        toon_output = formatter.format(data)
        json_output = json.dumps(data)

        # TOON should be at least 30% shorter (aiming for 50%+)
        reduction = 1 - (len(toon_output) / len(json_output))
        assert reduction > 0.3, f"Only {reduction * 100:.1f}% reduction, target >30%"


class TestToonEdgeCases:
    """Test TOON edge cases and error handling."""

    def test_encode_empty_dict(self):
        """Test encoding empty dictionary."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format({})

        assert result is not None

    def test_encode_empty_list(self):
        """Test encoding empty list."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()
        result = formatter.format([])

        assert "[]" in result

    def test_encode_string_with_special_chars(self):
        """Test encoding strings with special characters (should be quoted)."""
        from tree_sitter_analyzer_v2.formatters.toon_formatter import ToonFormatter

        formatter = ToonFormatter()

        # String with colon should be quoted
        result = formatter.format({"key": "value:with:colons"})
        assert "value:with:colons" in result

        # String with newline should be escaped
        result2 = formatter.format({"text": "line1\nline2"})
        assert "line1" in result2 and "line2" in result2
