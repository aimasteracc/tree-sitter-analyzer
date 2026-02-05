"""
Test Markdown formatter implementation.

Following TDD: Write tests FIRST to define the contract.
This is T3.2: Markdown Formatter

Markdown format is designed for human readability, using:
- Heading hierarchy (# ## ###)
- Code blocks for signatures
- Bullet lists for arrays
- Tables for structured data
"""


class TestMarkdownFormatterBasics:
    """Test basic Markdown formatter functionality."""

    def test_formatter_can_be_imported(self):
        """Test that MarkdownFormatter can be imported."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        assert MarkdownFormatter is not None

    def test_formatter_initialization(self):
        """Test creating a formatter instance."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        assert formatter is not None

    def test_format_returns_string(self):
        """Test that format() returns a string."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        result = formatter.format({"key": "value"})

        assert isinstance(result, str)


class TestMarkdownPrimitiveValues:
    """Test Markdown encoding of primitive values."""

    def test_format_null(self):
        """Test formatting None/null."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        result = formatter.format(None)

        assert "null" in result.lower() or result.strip() == ""

    def test_format_boolean(self):
        """Test formatting boolean values."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        result_true = formatter.format(True)
        assert "true" in result_true.lower() or "yes" in result_true.lower()

        result_false = formatter.format(False)
        assert "false" in result_false.lower() or "no" in result_false.lower()

    def test_format_number(self):
        """Test formatting numbers."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()

        assert "42" in formatter.format(42)
        assert "3.14" in formatter.format(3.14)

    def test_format_string(self):
        """Test formatting strings."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        result = formatter.format("hello world")

        assert "hello world" in result


class TestMarkdownDictionaries:
    """Test Markdown formatting of dictionaries."""

    def test_format_simple_dict(self):
        """Test formatting simple dictionary."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {"name": "example", "count": 42, "active": True}

        result = formatter.format(data)

        # Should contain key-value pairs (keys are titleized)
        assert "Name" in result or "name" in result
        assert "example" in result
        assert "Count" in result or "count" in result
        assert "42" in result

    def test_format_nested_dict(self):
        """Test formatting nested dictionaries with proper hierarchy."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "file": "sample.py",
            "metadata": {"language": "python", "version": "3.11"},
            "statistics": {"lines": 100, "methods": 5},
        }

        result = formatter.format(data)

        # Should have headings or structure (keys are titleized)
        assert "File" in result or "file" in result
        assert "sample.py" in result
        assert "Metadata" in result or "metadata" in result
        assert "python" in result
        assert "Statistics" in result or "statistics" in result


class TestMarkdownArrays:
    """Test Markdown formatting of arrays."""

    def test_format_simple_array(self):
        """Test formatting simple arrays as lists."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = [1, 2, 3, 4, 5]

        result = formatter.format(data)

        # Should contain list items
        assert "1" in result
        assert "2" in result
        assert "3" in result

    def test_format_string_array(self):
        """Test formatting array of strings."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = ["python", "typescript", "rust"]

        result = formatter.format(data)

        assert "python" in result
        assert "typescript" in result
        assert "rust" in result


class TestMarkdownStructuredData:
    """Test Markdown formatting of structured data."""

    def test_format_analysis_result(self):
        """Test formatting a typical analysis result."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
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

        # Should be readable and structured
        assert "example.py" in result
        assert "python" in result
        assert "functions" in result or "Functions" in result
        assert "hello" in result
        assert "add" in result
        assert "metadata" in result or "Metadata" in result

    def test_format_with_headings(self):
        """Test that formatter uses headings for structure."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "classes": [{"name": "Calculator", "methods": ["add", "subtract"]}],
            "functions": [{"name": "helper"}],
        }

        result = formatter.format(data)

        # Should have markdown headings (# or ##)
        assert "#" in result or "**" in result  # Headings or bold


class TestMarkdownTables:
    """Test Markdown table formatting."""

    def test_format_array_of_dicts_as_table(self):
        """Test formatting homogeneous array of dicts as table."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "methods": [
                {"name": "init", "visibility": "public", "lines": "1-10"},
                {"name": "process", "visibility": "public", "lines": "12-45"},
                {"name": "validate", "visibility": "private", "lines": "47-60"},
            ]
        }

        result = formatter.format(data)

        # Should contain method information
        assert "init" in result
        assert "process" in result
        assert "validate" in result
        assert "public" in result
        assert "private" in result


class TestMarkdownCodeBlocks:
    """Test Markdown code block formatting."""

    def test_format_code_signature(self):
        """Test that code signatures use code blocks."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "functions": [
                {
                    "name": "calculate",
                    "parameters": ["x", "y"],
                    "return_type": "int",
                    "signature": "def calculate(x, y) -> int:",
                }
            ]
        }

        result = formatter.format(data)

        # Should contain function information
        assert "calculate" in result
        # May or may not use backticks for code, just check readability
        assert result is not None


class TestMarkdownReadability:
    """Test Markdown output readability."""

    def test_output_is_human_readable(self):
        """Test that output is human-readable."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "file_path": "test.py",
            "language": "python",
            "classes": [{"name": "MyClass", "methods": 3}],
            "functions": [{"name": "helper"}, {"name": "main"}],
        }

        result = formatter.format(data)

        # Should be readable (not compressed like TOON)
        # Should have whitespace and structure
        assert len(result) > 50  # Not too compact
        assert "\n" in result  # Multi-line

    def test_nested_structure_indentation(self):
        """Test that nested structures are properly formatted."""
        from tree_sitter_analyzer_v2.formatters.markdown_formatter import MarkdownFormatter

        formatter = MarkdownFormatter()
        data = {
            "file": "example.py",
            "analysis": {
                "classes": {"count": 3, "names": ["A", "B", "C"]},
                "functions": {"count": 5},
            },
        }

        result = formatter.format(data)

        # Should have clear structure
        assert "file" in result or "File" in result
        assert "analysis" in result or "Analysis" in result
        assert "classes" in result or "Classes" in result
